"""Joey decision routing via the System One API (self-hosted qev server on Spark, or Baseten)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import SUPPORTED_FUNCTIONS, Settings, get_settings
from app.llm.schemas import LLMAlternative, LLMClassificationOutput

logger = logging.getLogger(__name__)

# One client for the process. A new TCP connection per ticket costs more than the
# classification code around it, and Joey is called once per request.
_shared: httpx.AsyncClient | None = None


@dataclass
class LLMUsageTracker:
    """Per-request call count and token totals reported by System One."""

    llm_calls: int = 0
    token_usage: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0, "total": 0})

    def record_usage(self, usage: dict[str, Any]) -> None:
        """Add one System One ``usage`` block."""
        self.llm_calls += 1
        incoming = int(usage.get("input_tokens") or 0)
        outgoing = int(usage.get("output_tokens") or 0)
        self.token_usage["input"] += incoming
        self.token_usage["output"] += outgoing
        self.token_usage["total"] += incoming + outgoing


def shared_client() -> httpx.AsyncClient:
    """Return the process-wide client, opening it on first use."""
    global _shared
    if _shared is None or _shared.is_closed:
        _shared = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _shared


def reset_shared_client() -> None:
    """Drop the cached client so the next call builds a new one. Used by tests."""
    global _shared
    _shared = None


async def aclose_shared_client() -> None:
    """Close the cached client. Called from the application lifespan."""
    global _shared
    client = _shared
    _shared = None
    if client is not None and not client.is_closed:
        await client.aclose()


def _settings(settings: Settings | None) -> Settings:
    return get_settings() if settings is None else settings


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
    ``criteria`` are ignored. The winning label is returned as is, including a low probability:
    ``unclassified`` is an option the model picks, not a threshold applied afterwards.
    """
    allowed = criteria if criteria is not None else _settings(None).joey_route_criteria
    raw_probs: dict[str, Any] = answer.get("probabilities") or {}
    probs = {str(key): float(value) for key, value in raw_probs.items() if str(key) in allowed}
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
    usage_tracker: LLMUsageTracker,
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

    timeout = httpx.Timeout(settings.joey_timeout_seconds)
    response = await shared_client().post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    usage = data.get("usage") or {}
    if hasattr(usage_tracker, "record_usage"):
        usage_tracker.record_usage(usage)
    elif hasattr(usage_tracker, "llm_calls"):
        usage_tracker.llm_calls += 1

    answers = data.get("answers") or {}
    route = answers.get("route")
    if not isinstance(route, dict):
        raise TypeError("System One response missing answers.route")

    return parse_choice_answer(route, criteria)
