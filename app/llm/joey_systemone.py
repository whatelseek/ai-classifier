"""Joey decision routing via the System One API (self-hosted qev server on Spark, or Baseten)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import SUPPORTED_FUNCTIONS, Settings, get_settings
from app.llm.schemas import LLMAlternative, LLMClassificationOutput

logger = logging.getLogger(__name__)


def _settings(settings: Settings | None) -> Settings:
    return get_settings() if settings is None else settings


def build_decision_state(body: str, merged_context: str) -> str:
    """Plain ``state`` string: the ticket text only."""
    parts: list[str] = []
    if (body or "").strip():
        parts.append(body.strip())
    merged = (merged_context or "").strip()
    if merged and merged != "(none)":
        parts.append(merged)
    return "\n\n".join(parts) if parts else "(empty)"


def build_route_questions(settings: Settings | None = None) -> dict[str, Any]:
    """One ``choice`` question: the four teams plus an explicit ``unclassified`` option.

    The question and each option's description come from settings (environment variables).
    """
    current = _settings(settings)
    return {
        "route": {
            "type": "choice",
            "instructions": current.joey_route_instructions,
            "criteria": dict(current.joey_route_criteria),
        }
    }


def parse_choice_answer(
    answer: dict[str, Any],
    criteria: dict[str, str] | None = None,
) -> LLMClassificationOutput:
    """Map a System One choice answer to ``LLMClassificationOutput``.

    ``confidence`` is the winning option's probability. Probabilities for labels outside
    ``criteria`` are ignored.
    """
    allowed = criteria if criteria is not None else _settings(None).joey_route_criteria
    raw_probs: dict[str, Any] = answer.get("probabilities") or {}
    probs = {str(k): float(v) for k, v in raw_probs.items() if str(k) in allowed}
    if not probs:
        raise ValueError("Missing probabilities in choice answer")

    ranked = sorted(probs.items(), key=lambda item: item[1], reverse=True)
    winner, top_prob = ranked[0]
    alternatives = [
        LLMAlternative(function=name, score=max(0.0, min(1.0, prob)))  # type: ignore[arg-type]
        for name, prob in ranked[1:]
        if name in SUPPORTED_FUNCTIONS
    ][:2]

    return LLMClassificationOutput(
        function=winner,  # type: ignore[arg-type]
        confidence=max(0.0, min(1.0, top_prob)),
        reason=f"Joey choice routing; top={winner} p={top_prob:.3f}",
        alternatives=alternatives,
        evidence=[],
    )


async def classify_via_systemone(
    settings: Settings,
    state: str,
    usage_tracker: Any,
) -> LLMClassificationOutput:
    """POST the routing question to a System One endpoint and parse the answer."""
    url = (settings.joey_systemone_url or "").rstrip("/")
    if not url:
        raise RuntimeError("JOEY_SYSTEMONE_URL is not configured")

    criteria = settings.joey_route_criteria
    payload = {
        "model": settings.joey_decision_model,
        "service_tier": "default",
        "state": state,
        "questions": build_route_questions(settings),
    }
    headers = {"Content-Type": "application/json"}
    # The self-hosted qev server takes no key; Baseten needs one.
    api_key = settings.resolved_systemone_api_key
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

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

    return parse_choice_answer(route, criteria)
