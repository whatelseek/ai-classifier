"""Tests for L1 ticket body extraction."""

from app.llm.ticket_body import extract_request_body


def test_chat_message_body():
    raw = (
        "Подготовь карточку разбора по обращению пользователя.\n\n"
        "[Сообщение в чат поддержки от m.lebedeva]\n"
        "почта не принимает письма"
    )
    assert extract_request_body(raw) == "почта не принимает письма"


def test_form_keeps_service_and_theme_with_opisanie():
    raw = (
        "Проанализируй заявку и вложения, составь карточку разбора.\n\n"
        "Выбранный сервис: Антивирусная защита\n"
        "Тема: антивирус мешает работать\n"
        "Описание:\nантивирус мешает работать"
    )
    out = extract_request_body(raw)
    assert "Антивирусная защита" in out
    assert "антивирус мешает работать" in out


def test_form_description_and_attachment():
    raw = (
        "Разбери обращение.\n\nНомер: TCK-1\nОписание:\nfailed password в ssh\n\n"
        "Вложения:\n\n<file name=\"auth.log\">sshd failed</file>"
    )
    out = extract_request_body(raw)
    assert "failed password" in out
    assert "auth.log" in out


def test_description_only_drops_inline_files():
    raw = (
        "Номер обращения: TCK-1\nТема: бэкап упал\nОписание:\nбэкап упал\n\n"
        "Вложения:\n\n<file name=\"job_report.txt\">\nError: Not enough free space\n</file>"
    )
    out = extract_request_body(raw, include_attachments=False)
    assert "бэкап упал" in out
    assert "job_report" not in out
    assert "free space" not in out


def test_description_only_drops_mail_headers_and_signature():
    raw = (
        "От: Иван Петров <i.petrov@corp.local>\nКому: helpdesk@corp.local\nТема: RE: Проблема\n\n"
        "Добрый день!\n\nдеплой упал помогите\n\n--\nС уважением,\nИван Петров\nтел. +7 931 920-89-68\n\n"
        "Вложения:\n\n<file name=\"describe.txt\">\nImagePullBackOff\n</file>"
    )
    assert extract_request_body(raw, include_attachments=False) == "деплой упал помогите"


def test_description_only_call_log():
    raw = (
        "Запись звонка на линию поддержки. Звонящий: Артём Соколов, логин a.sokolov.\n"
        "Со слов пользователя: потерял ноутбук"
    )
    assert extract_request_body(raw, include_attachments=False) == "потерял ноутбук"