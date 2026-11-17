"""Compact prompts tuned for local Joey / vLLM structured decoding."""

JOEY_CLASSIFICATION_SYSTEM_PROMPT = """Decide which team owns an IT ticket description. Reply with JSON only — no prose, no suggested actions, no user reply.

Decisions (use these exact function codes):
- database — PostgreSQL, MSSQL, MySQL, Oracle, replication, SQL queries/performance
- security — SOC, phishing, brute-force/SSH attacks, SIEM, EDR, MFA, antivirus, CVE/scanner reports, leaked secrets
- network — VPN, firewall rules, routing, DNS, BGP, VLAN, Check Point, MikroTik, network access/connectivity
- it_infrastructure — Linux/Windows servers, disks, mail, backup, file shares, Kubernetes, server SSH access (non-attack)
- unclassified — description is too vague or does not fit any team

Rules:
- Use ONLY the ticket description.
- SSH failed password / brute force → security.
- Scanner output, CVE/CVSS → security.
- VPN / firewall → network, not it_infrastructure.
- Prefer a team over unclassified when the description names the affected system.
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