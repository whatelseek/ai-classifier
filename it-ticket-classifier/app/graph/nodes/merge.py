"""LangGraph node: merge extracted chunks into one LLM context string."""

from app.core.config import get_settings
from app.core.security import sanitize_for_llm
from app.graph.state import AgentState


def merge_context(state: AgentState) -> dict:
    """Concatenate successful extraction chunks with source headers.

    Applies redaction and truncates to the configured token budget.

    Args:
        state: Graph state after parallel extraction branches complete.

    Returns:
        Partial update containing ``merged_context``.
    """
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

    return {"merged_context": merged}