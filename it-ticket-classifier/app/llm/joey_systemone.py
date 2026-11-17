"""Joey decision routing via Baseten System One (Playground score / choice API)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import SUPPORTED_FUNCTIONS, Settings
from app.llm.schemas import LLMAlternative, LLMClassificationOutput

logger = logging.getLogger(__name__)

PLAYGROUND_SCORE_INSTRUCTIONS = "К какой категории относится обращение?"
PLAYGROUND_SCORE_LEVELS: tuple[str, ...] = SUPPORTED_FUNCTIONS


def build_decision_state(body: str, merged_context: str) -> str:
    """Plain ``state`` string as in Baseten Playground (ticket text only)."""
    parts: list[str] = []
    if (body or "").strip():
        parts.append(body.strip())
    merged = (merged_context or "").strip()
    if merged and merged != "(none)":
        parts.append(merged)
    return "\n\n".join(parts) if parts else "(empty)"


def build_playground_score_questions() -> dict[str, Any]:
    """Score question matching Playground: ordered levels lowest → highest."""
    return {
        "route": {
            "type": "score",
            "instructions": PLAYGROUND_SCORE_INSTRUCTIONS,
            "criteria": list(PLAYGROUND_SCORE_LEVELS),
        }
    }


def parse_score_answer(
    answer: dict[str, Any],
    levels: tuple[str, ...] = PLAYGROUND_SCORE_LEVELS,
) -> LLMClassificationOutput:
    """Map System One score ``probabilities`` to ``LLMClassificationOutput``."""
    raw_probs: dict[str, float] = answer.get("probabilities") or {}
    if not raw_probs:
        raise ValueError("Missing probabilities in score answer")

    indexed = {int(k): float(v) for k, v in raw_probs.items()}
    winner_idx = max(indexed, key=indexed.get)
    if winner_idx < 0 or winner_idx >= len(levels):
        raise ValueError(f"Score level index out of range: {winner_idx}")

    function = levels[winner_idx]
    top_prob = indexed[winner_idx]
    conf = float(answer.get("confidence", top_prob))
    conf = max(0.0, min(1.0, conf))

    ranked = sorted(indexed.items(), key=lambda x: x[1], reverse=True)
    alternatives: list[LLMAlternative] = []
    for idx, prob in ranked[1:3]:
        if 0 <= idx < len(levels):
            alternatives.append(LLMAlternative(function=levels[idx], score=prob))  # type: ignore[arg-type]

    reason = (
        f"Joey score routing ({PLAYGROUND_SCORE_INSTRUCTIONS}); "
        f"top={function} p={top_prob:.3f}"
    )
    return LLMClassificationOutput(
        function=function,  # type: ignore[arg-type]
        confidence=conf,
        reason=reason[:240],
        alternatives=alternatives,
        evidence=[],
    )


async def classify_via_systemone(
    settings: Settings,
    state: str,
    usage_tracker: Any,
) -> LLMClassificationOutput:
    """POST /v1/systemone — same semantics as Baseten Joey Playground score."""
    url = (settings.joey_systemone_url or "").rstrip("/")
    if not url:
        raise RuntimeError("JOEY_SYSTEMONE_URL is not configured")
    api_key = settings.resolved_systemone_api_key
    if not api_key:
        raise RuntimeError("JOEY_SYSTEMONE_API_KEY / BASETEN_API_KEY is not configured")

    payload = {
        "model": settings.joey_decision_model,
        "service_tier": "default",
        "state": state,
        "questions": build_playground_score_questions(),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    timeout = httpx.Timeout(settings.openai_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    usage = data.get("usage") or {}
    if hasattr(usage_tracker, "record_systemone"):
        usage_tracker.record_systemone(usage)
    elif hasattr(usage_tracker, "llm_calls"):
        usage_tracker.llm_calls += 1
        if hasattr(usage_tracker, "token_usage"):
            usage_tracker.token_usage["input"] += int(usage.get("input_tokens") or 0)
            usage_tracker.token_usage["output"] += int(usage.get("output_tokens") or 0)
            usage_tracker.token_usage["total"] += int(usage.get("input_tokens") or 0) + int(
                usage.get("output_tokens") or 0
            )

    answers = data.get("answers") or {}
    route = answers.get("route")
    if not isinstance(route, dict):
        raise ValueError("System One response missing answers.route")

    return parse_score_answer(route)