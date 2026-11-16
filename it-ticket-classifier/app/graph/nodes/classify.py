"""LangGraph node: LLM or heuristic ticket function classification."""

import logging
import re

from app.core.config import SUPPORTED_FUNCTIONS, get_settings
from app.graph.state import AgentState
from app.llm.client import LLMUsageTracker, OpenAIClassificationClient
from app.llm.schemas import LLMClassificationOutput

logger = logging.getLogger(__name__)

# Heuristic patterns for offline / test mode when OpenAI is unavailable
HEURISTIC_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(vpn|ipsec|bgp|vlan|dns|mikrotik|check\s*point|firewall)\b", re.IGNORECASE), "network"),
    (re.compile(r"\b(postgres|postgresql|mysql|mssql|sql\s*server|replication|wal)\b", re.IGNORECASE), "database"),
    (re.compile(r"\b(systemd|ssh|ubuntu|debian|rhel|linux)\b", re.IGNORECASE), "linux"),
    (re.compile(r"\b(siem|edr|dlp|pam|security\s+incident|suspicious)\b", re.IGNORECASE), "security"),
]


async def classify_function(state: AgentState) -> dict:
    """Invoke the configured LLM or heuristic rules on merged context.

    Args:
        state: Graph state including description and ``merged_context``.

    Returns:
        Partial update with ``classification``, ``confidence``, and LLM counters.
    """
    settings = get_settings()
    client = OpenAIClassificationClient(settings)
    usage = LLMUsageTracker()
    merged = state.get("merged_context") or ""
    description = state.get("description") or ""

    if not merged.strip() and not description.strip():
        classification = {
            "function": "needs_review",
            "confidence": 0.0,
            "reason": "Insufficient evidence from description and attachments",
            "alternatives": [],
            "evidence": [],
        }
        return {
            "classification": classification,
            "confidence": 0.0,
            "status": "needs_review",
            "llm_calls": state.get("llm_calls", 0),
        }

    try:
        if client.is_available:
            result = await client.classify(
                description=description,
                merged_context=merged,
                client=state.get("client"),
                issue_key=state.get("issue_key"),
                usage=usage,
            )
            output = _from_llm(result)
        else:
            output = _heuristic_classify(description, merged)
            usage.llm_calls = 0
    except Exception as exc:
        logger.exception("Classification failed")
        return {
            "errors": [{"code": "classification_error", "message": str(exc)}],
            "status": "failed",
        }

    partial = {
        "classification": output,
        "confidence": output["confidence"],
        "llm_calls": (state.get("llm_calls") or 0) + usage.llm_calls,
        "token_usage": usage.token_usage,
    }
    if output["function"] == "needs_review":
        partial["status"] = "needs_review"
    else:
        partial["status"] = "classified"
    return partial


def _from_llm(result: LLMClassificationOutput) -> dict:
    """Convert a pydantic LLM payload into plain dict state."""
    return {
        "function": result.function,
        "confidence": result.confidence,
        "reason": result.reason,
        "alternatives": [{"function": a.function, "score": a.score} for a in result.alternatives],
        "evidence": list(result.evidence),
    }


def _heuristic_classify(description: str, merged: str) -> dict:
    """Keyword-based fallback when no API key is configured.

    Args:
        description: Ticket body.
        merged: Merged attachment text.

    Returns:
        Classification dict compatible with graph state.
    """
    text = f"{description}\n{merged}"
    scores: dict[str, float] = {f: 0.0 for f in SUPPORTED_FUNCTIONS}
    evidence: list[str] = []
    for pattern, func in HEURISTIC_RULES:
        if pattern.search(text):
            scores[func] += 0.5
            evidence.append(pattern.pattern)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_func, top_score = ranked[0]
    if top_score < 0.25:
        return {
            "function": "needs_review",
            "confidence": 0.2,
            "reason": "Heuristic classifier could not determine responsible function (no OpenAI key)",
            "alternatives": [],
            "evidence": evidence[:5],
        }
    alts = [
        {"function": f, "score": min(s, 1.0)}
        for f, s in ranked[1:]
        if s > 0
    ]
    return {
        "function": top_func,
        "confidence": min(0.85, 0.55 + top_score),
        "reason": f"Heuristic match for {top_func} responsibility indicators",
        "alternatives": alts,
        "evidence": evidence[:10],
    }