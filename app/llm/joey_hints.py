"""Body keyword hints when Joey/vLLM returns a generic structured head (often ``database``)."""

import re

from app.llm.schemas import LLMClassificationOutput

_PADDING_REASON_MARKERS = (
    "Structured model head",
    "vLLM output padding",
    "Recovered from partial model JSON",
)

_DATABASE_PATTERN = re.compile(
    r"postgres|postgresql|mysql|mssql|oracle|max_connections|репликац|sql\b|субд|баз[аеуы]\s+данн",
    re.IGNORECASE,
)

_BODY_HINTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"cve-\d{4}-\d+|cvss\b|уязвим|сканер|vulnerability|scan\s*report|"
            r"regresshion|terrapin|openssh\s+rce|jenkins.*cve",
            re.I,
        ),
        "security",
    ),
    (re.compile(r"failed\s+password|подбор\s+парол|brute|auth\.log|sshd\[|ssh\s+attack", re.I), "security"),
    (
        re.compile(
            r"антивирус|антивирусн|kaspersky|defender|dr\.?\s*web|edr\b|"
            r"фишинг|phishing|soc\b|siem|mfa\b|компрометац",
            re.I,
        ),
        "security",
    ),
    (
        re.compile(r"check\s*point|mikrotik|ipsec|vpn\b|впн|firewall|межсетев|bgp\b|vlan", re.IGNORECASE),
        "network",
    ),
    (_DATABASE_PATTERN, "database"),
    (
        re.compile(
            r"systemd|mdadm|raid|kubernetes|k8s\b|резервн|бэкап|veeam|почт|"
            r"диск|места?\s+на|disk|/var\b|сервер|linux|ssh\b|файлов",
            re.IGNORECASE,
        ),
        "it_infrastructure",
    ),
]


def should_apply_hints(result: LLMClassificationOutput) -> bool:
    """True when the LLM output looks like Joey padding salvage, not a full JSON reason."""
    reason = result.reason or ""
    return any(marker in reason for marker in _PADDING_REASON_MARKERS)


def adjust_joey_classification(body: str, result: LLMClassificationOutput) -> LLMClassificationOutput:
    """Re-map obvious body patterns when Joey defaulted to ``database`` / ``needs_review``."""
    if result.function not in ("database", "needs_review") and not should_apply_hints(result):
        return result
    blob = body or ""
    for pattern, function in _BODY_HINTS:
        if pattern.search(blob):
            if function == result.function:
                return result
            return LLMClassificationOutput(
                function=function,  # type: ignore[arg-type]
                confidence=min(0.85, max(result.confidence, 0.7)),
                reason=f"Joey body hint override ({pattern.pattern})",
                alternatives=list(result.alternatives),
                evidence=list(result.evidence),
            )
    # Padded Joey output defaults to ``database``; without database evidence it is a guess.
    if result.function == "database" and should_apply_hints(result) and not _DATABASE_PATTERN.search(blob):
        return LLMClassificationOutput(
            function="needs_review",
            confidence=0.0,
            reason="No team evidence in description",
        )
    return result