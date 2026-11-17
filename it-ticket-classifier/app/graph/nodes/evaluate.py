"""LangGraph nodes: confidence gating, retries, and response finalization."""

import logging
import time

from app.core.config import SUPPORTED_FUNCTIONS, get_settings
from app.graph.state import AgentState
from app.graph.telemetry import log_node

logger = logging.getLogger(__name__)


def evaluate_confidence(state: AgentState) -> dict:
    """Promote, downgrade, or flag classifications based on confidence.

    Args:
        state: State immediately after ``classify_function``.

    Returns:
        Partial state update adjusting ``status`` and possibly ``classification``.
    """
    started = time.perf_counter()
    classification = state.get("classification") or {}
    confidence = state.get("confidence", 0.0)
    func = classification.get("function")

    if state.get("status") in ("failed", "retry"):
        log_node(logger, "evaluate_confidence", started, status=state.get("status"))
        return {}

    if func == "needs_review":
        log_node(logger, "evaluate_confidence", started, status="needs_review", confidence=confidence)
        return {"status": "needs_review"}

    if confidence < 0.45:
        classification = {
            **classification,
            "function": "needs_review",
            "reason": classification.get("reason", "") + " (low confidence)",
        }
        log_node(logger, "evaluate_confidence", started, status="needs_review", confidence=confidence)
        return {
            "classification": classification,
            "status": "needs_review",
            "confidence": confidence,
        }

    if func not in SUPPORTED_FUNCTIONS:
        log_node(logger, "evaluate_confidence", started, status="needs_review")
        return {
            "status": "needs_review",
            "classification": {
                **classification,
                "function": "needs_review",
                "reason": "Invalid or missing function classification",
            },
        }

    if (
        confidence < 0.55
        and state.get("retry_count", 0) < get_settings().effective_max_classification_retries
    ):
        log_node(
            logger,
            "evaluate_confidence",
            started,
            status="classified",
            confidence=confidence,
            retry=True,
        )
        return {
            "status": "classified",
            "retry_feedback": (
                f"Previous attempt selected {func} with confidence {confidence:.2f}, "
                "below the acceptance threshold. Re-read the evidence and choose the "
                "team that must resolve the issue. If it is still ambiguous, return "
                "needs_review."
            ),
        }

    log_node(logger, "evaluate_confidence", started, status="classified", confidence=confidence)
    return {"status": "classified", "retry_feedback": ""}


def retry_classification(state: AgentState) -> dict:
    """Increment the bounded retry counter before re-classifying.

    Preserves ``retry_feedback`` from the previous node so the next model
    call explains why it is running again. When that note is missing, a
    low-confidence instruction is added here.

    Args:
        state: State routed to the retry path.

    Returns:
        Partial update with incremented ``retry_count`` and feedback text.
    """
    started = time.perf_counter()
    retry = state.get("retry_count", 0) + 1
    feedback = (state.get("retry_feedback") or "").strip()
    if not feedback:
        classification = state.get("classification") or {}
        feedback = (
            "Previous classification was not confident enough "
            f"(function={classification.get('function')}, "
            f"confidence={state.get('confidence')}). "
            "Reconsider the evidence or return needs_review."
        )
    log_node(logger, "retry_classification", started, retry_count=retry)
    return {"retry_count": retry, "retry_feedback": feedback}


def format_response(state: AgentState) -> dict:
    """Attach LLM usage metadata to the processing block.

    Args:
        state: Terminal or near-terminal graph state.

    Returns:
        Partial update merging token usage into ``processing``.
    """
    started = time.perf_counter()
    processing = dict(state.get("processing") or {})
    processing.setdefault("llm_calls", state.get("llm_calls", 0))
    usage = state.get("token_usage")
    if usage and (usage.get("total") or state.get("llm_calls")):
        processing["token_usage"] = dict(usage)
    log_node(
        logger,
        "format_response",
        started,
        status=state.get("status"),
        llm_calls=state.get("llm_calls", 0),
        retry_count=state.get("retry_count", 0),
    )
    return {"processing": processing}


def return_validation_error(state: AgentState) -> dict:
    """Terminal helper marking validation failure.

    Args:
        state: State with validation errors populated.

    Returns:
        Partial update with ``failed`` status.
    """
    return {"status": "failed"}