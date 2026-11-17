"""Support-routing label normalization."""

from app.core.config import SUPPORTED_FUNCTIONS, UNCLASSIFIED

_LEGACY_TO_CURRENT: dict[str, str] = {
    "linux": "it_infrastructure",
    UNCLASSIFIED: "needs_review",
}

_ROUTING_SET = frozenset(SUPPORTED_FUNCTIONS)


def normalize_routing_function(func: str | None) -> str:
    """Map model output (incl. legacy labels) to current routing codes."""
    if not func:
        return "needs_review"
    key = func.strip().lower()
    if key == "needs_review":
        return "needs_review"
    if key in _LEGACY_TO_CURRENT:
        return _LEGACY_TO_CURRENT[key]
    if key in _ROUTING_SET:
        return key
    return "needs_review"


def to_decision(func: str | None) -> str:
    """Public decision label: one of the supported teams or ``unclassified``."""
    normalized = normalize_routing_function(func)
    return normalized if normalized in _ROUTING_SET else UNCLASSIFIED