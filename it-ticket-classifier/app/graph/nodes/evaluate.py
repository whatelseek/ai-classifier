"""LangGraph nodes: confidence gating, retries, and response finalization."""

from app.graph.state import AgentState


def evaluate_confidence(state: AgentState) -> dict:
    """Promote, downgrade, or flag classifications based on confidence.

    Args:
        state: State immediately after ``classify_function``.

    Returns:
        Partial state update adjusting ``status`` and possibly ``classification``.
    """
    classification = state.get("classification") or {}
    confidence = state.get("confidence", 0.0)
    func = classification.get("function")

    if state.get("status") == "failed":
        return {}

    if func == "needs_review":
        return {"status": "needs_review"}

    if confidence < 0.45:
        classification = {
            **classification,
            "function": "needs_review",
            "reason": classification.get("reason", "") + " (low confidence)",
        }
        return {
            "classification": classification,
            "status": "needs_review",
            "confidence": confidence,
        }

    if func not in ("network", "linux", "security", "database"):
        return {
            "status": "needs_review",
            "classification": {
                **classification,
                "function": "needs_review",
                "reason": "Invalid or missing function classification",
            },
        }

    return {"status": "classified"}


def retry_classification(state: AgentState) -> dict:
    """Increment the bounded retry counter before re-classifying.

    Args:
        state: State routed to the retry path.

    Returns:
        Partial update with incremented ``retry_count``.
    """
    retry = state.get("retry_count", 0) + 1
    return {"retry_count": retry}


def format_response(state: AgentState) -> dict:
    """Attach LLM usage metadata to the processing block.

    Args:
        state: Terminal or near-terminal graph state.

    Returns:
        Partial update merging token usage into ``processing``.
    """
    processing = state.get("processing") or {}
    processing.setdefault("llm_calls", state.get("llm_calls", 0))
    if state.get("token_usage"):
        processing["token_usage"] = state.get("token_usage")
    return {"processing": processing}


def return_validation_error(state: AgentState) -> dict:
    """Terminal helper marking validation failure.

    Args:
        state: State with validation errors populated.

    Returns:
        Partial update with ``failed`` status.
    """
    return {"status": "failed"}