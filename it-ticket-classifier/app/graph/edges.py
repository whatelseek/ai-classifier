"""Conditional routing helpers for the LangGraph classification workflow."""

from typing import Literal

from langgraph.types import Send

from app.core.config import get_settings
from app.graph.state import AgentState

RouteAfterValidate = Literal["detect_attachments", "return_validation_error"]
RouteAfterConfidence = Literal["format_response", "retry_classification", "needs_review_path"]


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


def fan_out_processing(state: AgentState) -> list[Send]:
    """Fan out to parallel attachment branches using LangGraph ``Send``.

    Skips branches that have no matching content. When nothing needs
    extraction, sends directly to ``merge_context``.

    Args:
        state: Current graph state including ``branches`` flags.

    Returns:
        List of ``Send`` commands targeting process_* or merge nodes.
    """
    branches = state.get("branches") or {}
    sends: list[Send] = []
    if branches.get("text"):
        sends.append(Send("process_text", state))
    if branches.get("docs"):
        sends.append(Send("process_documents", state))
    if branches.get("images"):
        sends.append(Send("process_images", state))
    if branches.get("diagrams"):
        sends.append(Send("process_diagrams", state))
    if not sends:
        sends.append(Send("merge_context", state))
        return sends
    return sends


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

    if status == "needs_review" or func == "needs_review":
        return "needs_review_path"

    if confidence < 0.55 and retry_count < settings.max_classification_retries:
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