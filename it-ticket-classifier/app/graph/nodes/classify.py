"""LangGraph node: LLM or heuristic ticket function classification."""

import logging
import re
import time

from langgraph.errors import NodeError
from langgraph.runtime import Runtime

from app.core.config import SUPPORTED_FUNCTIONS, get_settings
from app.core.errors import CLASSIFICATION_FAILED
from app.graph.context import GraphContext, llm_from_runtime
from app.graph.state import AgentState
from app.graph.telemetry import log_node
from app.llm.client import LLMUsageTracker, is_transient_llm_error
from app.llm.schemas import LLMClassificationOutput

logger = logging.getLogger(__name__)

# Heuristic patterns for offline / test mode when OpenAI is unavailable
HEURISTIC_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(vpn|ipsec|bgp|vlan|dns|mikrotik|check\s*point|firewall)\b", re.IGNORECASE), "network"),
    (
        re.compile(
            r"\b(postgres|postgresql|mysql|mssql|sql\s*server|replication|wal|"
            r"субд|баз[аы]\s+данн|индекс|резервн|репликац)\b",
            re.IGNORECASE,
        ),
        "database",
    ),
    (re.compile(r"\b(systemd|ssh|ubuntu|debian|rhel|linux)\b", re.IGNORECASE), "linux"),
    (re.compile(r"\b(siem|edr|dlp|pam|security\s+incident|suspicious)\b", re.IGNORECASE), "security"),
]


async def classify_function(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    """Invoke the configured LLM or heuristic rules on merged context.

    Transient API errors propagate so the node ``RetryPolicy`` can repeat the
    call. Invalid model output is stored as ``retry`` until the retry budget
    is spent, and the next prompt includes ``retry_feedback``.

    Args:
        state: Graph state including description and ``merged_context``.
        runtime: Runtime context carrying the shared LLM client.

    Returns:
        Partial update with ``classification``, ``confidence``, and LLM deltas.
    """
    started = time.perf_counter()
    settings = get_settings()
    client = llm_from_runtime(runtime)
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
        log_node(logger, "classify_function", started, status="needs_review", function="needs_review")
        return {
            "classification": classification,
            "confidence": 0.0,
            "status": "needs_review",
        }

    try:
        if client.is_available:
            result = await client.classify(
                description=description,
                merged_context=merged,
                client=state.get("client"),
                issue_key=state.get("issue_key"),
                usage=usage,
                retry_feedback=state.get("retry_feedback") or None,
            )
            output = _from_llm(result)
        else:
            output = _heuristic_classify(description, merged)
            usage.llm_calls = 0
    except Exception as exc:
        if is_transient_llm_error(exc):
            logger.exception("Transient classification error")
            raise
        logger.exception("Classification output rejected")
        partial = _invalid_output_update(state, exc, settings.effective_max_classification_retries)
        log_node(
            logger,
            "classify_function",
            started,
            status=partial["status"],
            retry_count=state.get("retry_count", 0),
        )
        return partial

    partial = {
        "classification": output,
        "confidence": output["confidence"],
        "llm_calls": usage.llm_calls,
        "token_usage": usage.token_usage,
        "retry_feedback": "",
        "status": "needs_review" if output["function"] == "needs_review" else "classified",
    }
    log_node(
        logger,
        "classify_function",
        started,
        status=partial["status"],
        function=output["function"],
        confidence=output["confidence"],
        llm_calls=usage.llm_calls,
        retry_count=state.get("retry_count", 0),
    )
    return partial


def _invalid_output_update(state: AgentState, exc: Exception, max_retries: int) -> dict:
    """Route an invalid model payload back into the retry loop.

    Args:
        state: Graph state, used for the current retry count.
        exc: Parse or schema error. Its text is not returned to the client.
        max_retries: Maximum classification retries from settings.

    Returns:
        Partial state with ``retry`` or terminal ``failed`` status.
    """
    feedback = (
        f"Previous response could not be parsed ({type(exc).__name__}). "
        "Return a JSON object with function, confidence, reason, alternatives, "
        "and evidence. Use needs_review when evidence is insufficient."
    )
    if state.get("retry_count", 0) < max_retries:
        return {"status": "retry", "retry_feedback": feedback}
    return {
        "status": "failed",
        "retry_feedback": "",
        "errors": [{"code": "classification_error", "message": CLASSIFICATION_FAILED}],
    }


def classification_error_handler(state: AgentState, error: NodeError) -> dict:
    """Record a terminal classification failure after retries are exhausted.

    Args:
        state: Graph state at the failed attempt.
        error: Node failure context. The exception text is logged, not returned.

    Returns:
        Partial update with ``failed`` status and a stable error code.
    """
    del state
    logger.error("Classification node %s failed", error.node, exc_info=error.error)
    return {
        "status": "failed",
        "errors": [{"code": "classification_error", "message": CLASSIFICATION_FAILED}],
    }


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