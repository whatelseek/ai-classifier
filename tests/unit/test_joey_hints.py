"""Joey body hint overrides for padding-salvage misroutes."""

from app.llm.joey_hints import adjust_joey_classification
from app.llm.schemas import LLMClassificationOutput
from app.llm.ticket_body import extract_request_body


def _database_pad() -> LLMClassificationOutput:
    return LLMClassificationOutput(
        function="database",
        confidence=0.72,
        reason="Structured model head (vLLM output padding removed)",
        alternatives=[],
        evidence=[],
    )


def test_scanner_cve_report_maps_to_security():
    raw = """Классифицируй обращение и предложи действия.
Описание:
отчет сканера что делать
Вложения:
<file name="scan_report.csv">
10.50.1.14;8080;CVE-2024-23897;9.8;Jenkins arbitrary file read
</file>"""
    body = extract_request_body(raw)
    out = adjust_joey_classification(body, _database_pad())
    assert out.function == "security"
    assert "Joey body hint override" in out.reason


def test_postgres_keeps_database_when_no_security_signal():
    body = "Плановое обслуживание PostgreSQL и проверка репликации"
    out = adjust_joey_classification(body, _database_pad())
    assert out.function == "database"


def test_disk_full_maps_to_it_infrastructure():
    out = adjust_joey_classification("на сервере закончилось место на диске /var", _database_pad())
    assert out.function == "it_infrastructure"


def test_padded_database_without_evidence_is_unclassified():
    out = adjust_joey_classification("Помогите пожалуйста", _database_pad())
    assert out.function == "needs_review"


def test_postgres_on_server_stays_database():
    out = adjust_joey_classification("ошибка на сервере PostgreSQL", _database_pad())
    assert out.function == "database"