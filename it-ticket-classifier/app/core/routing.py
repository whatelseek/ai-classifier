"""Support-routing label normalization."""

from app.core.config import SUPPORTED_FUNCTIONS

_LEGACY_TO_CURRENT: dict[str, str] = {
    "network": "it_infrastructure",
    "linux": "it_infrastructure",
}

_ROUTING_SET = frozenset(SUPPORTED_FUNCTIONS)


def normalize_routing_function(func: str | None) -> str:
    """Map model output (incl. legacy four-way labels) to current routing codes."""
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