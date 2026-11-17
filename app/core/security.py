"""Redact secrets and private addresses before text is sent to Joey."""

import re

SECRET_PATTERNS: list[re.Pattern[str]] = [
    # The whole PEM block. Without an END line, the header and the base64 lines after it.
    re.compile(
        r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"
        r"(?:.*?-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|(?:\s+[A-Za-z0-9+/=]{20,})*)",
        re.DOTALL,
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_-]?key|password|passwd|pwd|secret|token|пароль|токен)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    # Provider tokens that are recognisable without a label.
    re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_\-]{20,}"
        r"|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9\-]{10,})"
    ),
]

INTERNAL_HOST_PATTERN = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3})\b"
)


def mask_secrets(text: str) -> str:
    """Replace detected secrets and credentials with a redaction token."""
    masked = text
    for pattern in SECRET_PATTERNS:
        masked = pattern.sub("[REDACTED_SECRET]", masked)
    return masked


def mask_infrastructure(text: str, mask_hosts: bool = True) -> str:
    """Mask private RFC1918 addresses when policy requires it."""
    if not mask_hosts:
        return text
    return INTERNAL_HOST_PATTERN.sub("[REDACTED_IP]", text)


def sanitize_for_llm(text: str, mask_hosts: bool = True) -> str:
    """Apply secret and infrastructure masking before the text leaves the service."""
    return mask_infrastructure(mask_secrets(text), mask_hosts=mask_hosts)
