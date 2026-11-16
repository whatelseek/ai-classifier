"""LangGraph node: merge extracted chunks into one LLM context string."""

import logging
import time

from app.core.config import get_settings
from app.core.security import sanitize_for_llm
from app.graph.state import AgentState
from app.graph.telemetry import log_node

logger = logging.getLogger(__name__)


def merge_context(state: AgentState) -> dict:
    """Concatenate successful extraction chunks with source headers.

    Applies redaction and truncates to the configured token budget.

    Args:
        state: Graph state after parallel extraction branches complete.

    Returns:
        Partial update containing ``merged_context``.
    """
    started = time.perf_counter()
    parts: list[str] = []
    for chunk in state.get("extracted_content") or []:
        if chunk.get("status") != "processed":
            continue
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        ref = chunk.get("source_ref") or chunk.get("filename")
        parts.append(f"--- {ref} ({chunk.get('parser')}) ---\n{text}")

    merged = sanitize_for_llm("\n\n".join(parts))
    max_chars = get_settings().openai_max_input_tokens * 4
    if len(merged) > max_chars:
        merged = merged[:max_chars] + "\n...[truncated]"

    log_node(logger, "merge_context", started, chunks=len(parts), chars=len(merged))
    return {"merged_context": merged}