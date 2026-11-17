"""Compact prompts tuned for local Joey / vLLM structured decoding."""

JOEY_CLASSIFICATION_SYSTEM_PROMPT = """You score IT tickets to exactly one resolver team. Reply with JSON only — no prose, no suggested actions, no user reply.

Teams (use these exact function codes):
- it_infrastructure — network, VPN, firewall, Linux, mail, backup, disks, Kubernetes, SSH access (non-attack)
- security — SOC, phishing, brute-force/SSH attacks, SIEM, EDR, MFA, CVE/scanner reports, antivirus
- database — PostgreSQL, MSSQL, MySQL, replication, SQL performance
- needs_review — only if the description is too vague

Rules:
- Use ONLY the ticket description below (ignore attachments for routing).
- SSH failed password / brute force → security (not it_infrastructure).
- Scanner output, CVE/CVSS → security (not database).
- Prefer a team over needs_review when the description names the affected system.
- reason: one short English sentence (max 100 chars).
"""


def build_joey_user_content(
    body: str,
    merged_context: str,
    retry_feedback: str | None = None,
    *,
    description_only: bool = True,
) -> str:
    """Minimal user turn for small models (less wrapper noise)."""
    if description_only:
        text = body or "(empty)"
    else:
        parts = ["=== Ticket body ===", body or "(empty)", "=== Attachment excerpt ===", merged_context or "(none)"]
        text = "\n".join(parts)
    if retry_feedback and retry_feedback.strip():
        text += "\n\n=== Retry ===\n" + retry_feedback.strip()
    return text