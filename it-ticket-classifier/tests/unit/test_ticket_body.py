"""Tests for L1 ticket body extraction."""

from app.llm.ticket_body import extract_request_body


def test_chat_message_body():
    raw = (
        "Подготовь карточку разбора по обращению пользователя.\n\n"
        "[Сообщение в чат поддержки от m.lebedeva]\n"
        "почта не принимает письма"
    )
    assert extract_request_body(raw) == "почта не принимает письма"


def test_form_description_and_attachment():
    raw = (
        "Разбери обращение.\n\nНомер: TCK-1\nОписание:\nfailed password в ssh\n\n"
        "Вложения:\n\n<file name=\"auth.log\">sshd failed</file>"
    )
    out = extract_request_body(raw)
    assert "failed password" in out
    assert "auth.log" in out