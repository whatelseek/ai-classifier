"""LangGraph node: validate minimum input requirements."""

import logging
import time

from app.graph.state import AgentState
from app.graph.telemetry import log_node

logger = logging.getLogger(__name__)


def validate_request(state: AgentState) -> dict:
    """Ensure at least description text or attachments are present.

    Args:
        state: Incoming graph state before extraction.

    Returns:
        Partial update with ``validated`` status or validation errors.
    """
    started = time.perf_counter()
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
        log_node(logger, "validate_request", started, status="failed")
        return {"status": "failed", "errors": errors}

    log_node(logger, "validate_request", started, status="validated", files=len(attachments))
    return {"status": "validated", "description": description}