"""Compact prompts tuned for local Joey / vLLM structured decoding."""

JOEY_CLASSIFICATION_SYSTEM_PROMPT = """You score IT tickets to exactly one resolver team. Reply with JSON only — no prose, no suggested actions, no user reply.

Teams:
- network — VPN, firewall, routing, DNS, Check Point, MikroTik
- linux — Linux OS, systemd, mail servers, backup, disks, Kubernetes, SSH access (non-attack)
- security — SOC, phishing, brute-force/SSH password guessing, SIEM, EDR, MFA, vulnerability scans/CVE reports, certificates as security
- database — PostgreSQL, MSSQL, MySQL, replication, SQL performance
- needs_review — only if the body is too vague

Rules:
- Use ONLY the ticket body and attachment excerpt below.
- SSH failed password / brute force / auth.log attacks → security (not linux).
- Scanner output, CVE/CVSS, vulnerability management → security (not database).
- User mail delivery / postfix/exchange symptoms → linux unless clearly phishing.
- Prefer a team over needs_review when the body names the affected system.
- reason: one short English sentence (max 100 chars).
"""


def build_joey_user_content(body: str, merged_context: str, retry_feedback: str | None = None) -> str:
    """Minimal user turn for small models (less wrapper noise)."""
    parts = ["=== Ticket body ===", body or "(empty)", "=== Attachment excerpt ===", merged_context or "(none)"]
    text = "\n".join(parts)
    if retry_feedback and retry_feedback.strip():
        text += "\n\n=== Retry ===\n" + retry_feedback.strip()
    return text