"""Conditional routing helpers for the LangGraph classification workflow."""

from typing import Literal

from langgraph.types import Send

from app.core.config import get_settings
from app.graph.state import AgentState
from app.parsers.registry import category_for_filename

RouteAfterValidate = Literal["detect_attachments", "return_validation_error"]
RouteAfterConfidence = Literal["format_response", "retry_classification", "needs_review_path"]

_DOCUMENT_CATEGORIES = frozenset(
    {"document", "presentation", "spreadsheet", "text", "structured"}
)


def route_after_validate(state: AgentState) -> RouteAfterValidate:
    """Route after request validation.

    Args:
        state: Current graph state.

    Returns:
        Next node name depending on validation status.
    """
    if state.get("status") == "failed":
        return "return_validation_error"
    return "detect_attachments"


def branch_node_for_filename(filename: str) -> str | None:
    """Map one attachment to the extraction node that should parse it.

    Args:
        filename: Upload filename.

    Returns:
        Node name, or ``None`` when the extension has no parser.
    """
    category = category_for_filename(filename)
    if category == "image":
        return "process_images"
    if category == "diagram":
        return "process_diagrams"
    if category in _DOCUMENT_CATEGORIES:
        return "process_documents"
    return None


def fan_out_processing(state: AgentState) -> list[Send]:
    """Fan out one ``Send`` per attachment, plus the description branch.

    Each worker receives only its own attachment so a failure can be retried
    without re-parsing siblings. ``max_concurrency`` on invoke caps how many
    of those workers run at once. When nothing needs extraction, sends
    directly to ``merge_context``.

    Args:
        state: Current graph state including description and attachments.

    Returns:
        List of ``Send`` commands targeting process_* or merge nodes.
    """
    sends: list[Send] = []
    if (state.get("description") or "").strip():
        sends.append(Send("process_text", _worker_state(state, [])))

    for attachment in state.get("attachments") or []:
        target = branch_node_for_filename(attachment["filename"])
        if target is None:
            continue
        sends.append(Send(target, _worker_state(state, [attachment])))

    if not sends:
        sends.append(Send("merge_context", _worker_state(state, [])))
    return sends


def _worker_state(state: AgentState, attachments: list) -> dict:
    """Build the input view for one fan-out worker.

    Reducer channels are omitted so the worker input is not applied as a
    parent-state write. Nodes return only the chunks they produce.

    Args:
        state: Parent graph state.
        attachments: Attachments owned by this worker.

    Returns:
        Mapping passed as the ``Send`` argument.
    """
    return {
        "request_id": state.get("request_id", ""),
        "issue_key": state.get("issue_key"),
        "client": state.get("client"),
        "description": state.get("description") or "",
        "attachments": attachments,
        "retry_count": state.get("retry_count", 0),
        "status": state.get("status", "pending"),
    }


def route_after_fanout(state: AgentState) -> Literal["merge_context"]:
    """Legacy edge helper always targeting merge (unused in current builder).

    Args:
        state: Current graph state.

    Returns:
        Literal name ``merge_context``.
    """
    return "merge_context"


def route_after_confidence(state: AgentState) -> RouteAfterConfidence:
    """Decide whether to finalize, retry, or flag manual review.

    Args:
        state: State after confidence evaluation.

    Returns:
        Next edge key for the conditional router.
    """
    settings = get_settings()
    status = state.get("status")
    confidence = state.get("confidence", 0.0)
    retry_count = state.get("retry_count", 0)
    classification = state.get("classification") or {}
    func = classification.get("function")

    if status == "failed":
        return "format_response"

    if status == "retry":
        if retry_count < settings.effective_max_classification_retries:
            return "retry_classification"
        return "format_response"

    if status == "needs_review" or func == "needs_review":
        return "needs_review_path"

    if confidence < 0.55 and retry_count < settings.effective_max_classification_retries:
        return "retry_classification"

    return "format_response"


def mark_needs_review(state: AgentState) -> dict:
    """Normalize classification output for manual review queue.

    Args:
        state: Current graph state.

    Returns:
        Partial state update forcing ``needs_review`` status.
    """
    classification = state.get("classification") or {}
    return {
        "status": "needs_review",
        "classification": {
            **classification,
            "function": "needs_review",
        },
    }