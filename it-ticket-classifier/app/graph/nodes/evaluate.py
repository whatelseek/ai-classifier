from app.graph.state import AgentState


def evaluate_confidence(state: AgentState) -> dict:
    classification = state.get("classification") or {}
    confidence = state.get("confidence", 0.0)
    func = classification.get("function")

    if state.get("status") == "failed":
        return {}

    if func == "needs_review":
        return {"status": "needs_review"}

    # Low confidence -> needs review
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

    # Schema guard: primary must be in enum (needs_review handled above)
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
    retry = state.get("retry_count", 0) + 1
    return {"retry_count": retry}


def format_response(state: AgentState) -> dict:
    processing = state.get("processing") or {}
    processing.setdefault("llm_calls", state.get("llm_calls", 0))
    if state.get("token_usage"):
        processing["token_usage"] = state.get("token_usage")
    return {"processing": processing}


def return_validation_error(state: AgentState) -> dict:
    return {"status": "failed"}