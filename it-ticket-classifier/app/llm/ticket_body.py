"""Extract the user request body from L1 helpdesk wrapper text."""

import re


_INSTRUCTION_PREFIXES = (
    "Подготовь карточку разбора",
    "Разбери обращение",
    "Проанализируй заявку",
    "Классифицируй обращение",
    "Классифицируй обращение и предложи действия",
)

_META_LINE_PREFIXES = (
    "Номер обращения:",
    "Заявитель:",
    "Контактный телефон:",
    "Контакт:",
    "Выбранный сервис:",
)


def extract_request_body(description: str) -> str:
    """Return the incident narrative without L1 triage instructions or form headers.

    Args:
        description: Raw ticket text from the API or training user turn.

    Returns:
        Shortened body suitable for routing classification.
    """
    text = (description or "").strip()
    if not text:
        return text

    for prefix in _INSTRUCTION_PREFIXES:
        if text.startswith(prefix):
            text = re.sub(r"^[^\n]+\n+", "", text, count=1)
            break

    chat = re.search(
        r"\[(?:Сообщение|Message)[^\]]*\]\s*(?:от\s+[^\n]+)?\s*\n?(.+)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if chat:
        body = chat.group(1).strip()
        return _cap(body)

    if "Описание:" in text:
        parts = _routing_context_lines(text)
        tail = text.split("Описание:", 1)[1]
        if "Вложения:" in tail:
            desc_part, att_part = tail.split("Вложения:", 1)
            parts.append(desc_part.strip())
            att = att_part.strip()
            if att:
                parts.append(att)
            return _cap("\n\n".join(parts))
        parts.append(tail.strip())
        return _cap("\n\n".join(parts))

    if "Тема:" in text:
        lines = text.splitlines()
        kept: list[str] = []
        skip_meta = True
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if kept:
                    kept.append("")
                continue
            if stripped.startswith("Тема:"):
                kept.append(stripped)
                skip_meta = False
                continue
            if skip_meta and any(stripped.startswith(p) for p in _META_LINE_PREFIXES):
                continue
            if stripped == "Описание:":
                continue
            if stripped.startswith("Вложения:"):
                kept.append(stripped)
                continue
            kept.append(line)
        if kept:
            return _cap("\n".join(kept).strip())

    # Email-style: keep subject + first non-signature block
    if "Тема:" in text or "Subject:" in text.lower():
        return _cap(text)

    return _cap(text)


def _routing_context_lines(text: str) -> list[str]:
    """Keep service and subject lines for routing (dropped from triage narrative)."""
    lines: list[str] = []
    for key in ("Выбранный сервис:", "Тема:"):
        match = re.search(rf"^{re.escape(key)}\s*(.+)$", text, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if value:
                lines.append(f"{key} {value}")
    return lines


def _cap(text: str, limit: int = 8000) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"