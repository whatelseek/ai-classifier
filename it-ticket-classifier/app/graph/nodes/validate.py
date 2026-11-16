"""LangGraph node: validate minimum input requirements."""

import logging

from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def validate_request(state: AgentState) -> dict:
    """Ensure at least description text or attachments are present.

    Args:
        state: Incoming graph state before extraction.

    Returns:
        Partial update with ``validated`` status or validation errors.
    """
    description = (state.get("description") or "").strip()
    attachments = state.get("attachments") or []
    errors: list[dict[str, str]] = []

    if not description and not attachments:
        errors.append(
            {
                "code": "validation_error",
                "message": "At least one of description or files must be provided",
            }
        )
        return {"status": "failed", "errors": errors}

    return {"status": "validated", "description": description}