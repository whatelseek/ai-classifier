"""System and user prompt templates for ticket classification."""

CLASSIFICATION_SYSTEM_PROMPT = """You are an IT support routing classifier for an enterprise service desk.

Your task is to assign exactly ONE primary IT support function responsible for resolving the ticket.

Supported functions (exact JSON codes):
1. it_infrastructure — IT-infrastructure: network, VPN, firewalls, Linux/OS, mail, backup, Kubernetes, storage.
2. security — Security: SIEM, EDR, phishing, incidents, vulnerability/CVE reports, antivirus.
3. database — Database: PostgreSQL, SQL Server, MySQL, replication, SQL performance.

Rules:
- Classify by the team that must RESOLVE the issue using the ticket description only.
- If evidence is insufficient or highly ambiguous across functions, set function to "needs_review" with low confidence.
- Return structured JSON matching the required schema only. No markdown or extra text.
- Output `function` first in the JSON object (field order: function, confidence, reason, alternatives, evidence).
- `reason`: one short sentence in English, at most 120 characters.
- `alternatives`: at most two entries; omit when unnecessary.
- `evidence`: at most five short phrases (under 80 characters each).

Examples:
- "Configure IPsec VPN between Check Point and MikroTik" -> it_infrastructure
- "PostgreSQL replication is broken" -> database
- "Linux systemd service fails to start" -> it_infrastructure
- "Investigate suspicious activity detected by SIEM" -> security
"""


def build_classification_user_content(
    description: str,
    merged_context: str,
    client: str | None,
    issue_key: str | None,
    retry_feedback: str | None = None,
    max_chars: int | None = None,
    *,
    description_only: bool = True,
) -> str:
    """Assemble the user message with metadata, description, and attachment text.

    When ``retry_feedback`` is set, it is appended after truncation so a retry
    sees a different instruction than the first attempt.

    Args:
        description: Ticket narrative.
        merged_context: Sanitized text merged from parsers.
        client: Optional client identifier.
        issue_key: Optional external ticket key.
        retry_feedback: Extra instruction for a low-confidence or invalid retry.
        max_chars: Optional cap applied to the ticket body before the retry note.

    Returns:
        Single string sent as the user turn to the LLM.
    """
    parts = ["=== Ticket metadata ==="]
    if issue_key:
        parts.append(f"Issue key: {issue_key}")
    if client:
        parts.append(f"Client: {client}")
    parts.append("\n=== Ticket description ===")
    parts.append(description or "(no description provided)")
    if not description_only:
        parts.append("\n=== Extracted attachment context ===")
        parts.append(merged_context or "(no attachment content)")
    parts.append(
        "\nClassify the primary responsible IT support function from the description. "
        "Return needs_review if evidence is insufficient."
    )
    text = "\n".join(parts)
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    if retry_feedback and retry_feedback.strip():
        text += "\n\n=== Retry instruction ===\n" + retry_feedback.strip()
    return text