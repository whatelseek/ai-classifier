from typing import Literal

from langgraph.types import Send

from app.core.config import get_settings
from app.graph.state import AgentState

RouteAfterValidate = Literal["detect_attachments", "return_validation_error"]
RouteAfterConfidence = Literal["format_response", "retry_classification", "needs_review_path"]


def route_after_validate(state: AgentState) -> RouteAfterValidate:
    if state.get("status") == "failed":
        return "return_validation_error"
    return "detect_attachments"


def fan_out_processing(state: AgentState) -> list[Send]:
    """Dynamic fan-out to parallel processing branches when needed."""
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
        # No text and no attachments content branches — still merge/classify
        sends.append(Send("merge_context", state))
        return sends
    return sends


def route_after_fanout(state: AgentState) -> Literal["merge_context"]:
    return "merge_context"


def route_after_confidence(state: AgentState) -> RouteAfterConfidence:
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
    classification = state.get("classification") or {}
    return {
        "status": "needs_review",
        "classification": {
            **classification,
            "function": "needs_review",
        },
    }