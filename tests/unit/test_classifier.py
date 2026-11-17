"""Service behaviour that does not need the HTTP stack."""

import time

import httpx

from app.core.config import Settings
from app.llm import joey_systemone
from app.llm.joey_systemone import reset_shared_client
from app.llm.schemas import LLMClassificationOutput
from app.models.responses import ResponseStatus
from app.services.classifier import ClassificationService

_TICKET = (
    "Сервер 10.1.2.3 недоступен, password=Qwerty123! "
    "токен ghp_abcdefghijklmnopqrstuvwxyz0123456789"
)


async def test_description_is_masked_before_it_is_sent():
    seen: list[str] = []

    async def capture(settings, state, usage):
        seen.append(state)
        return LLMClassificationOutput(function="security", confidence=0.431, reason="masked")

    service = ClassificationService(
        Settings(_env_file=None, JOEY_SYSTEMONE_URL="http://joey.test/v1/systemone"),
        backend=capture,
    )
    response = await service.classify(_TICKET)
    assert response.decision == "security"
    assert response.status is ResponseStatus.classified
    assert response.classification is not None
    assert response.classification.confidence == 0.431
    state = seen[0]
    assert "10.1.2.3" not in state
    assert "Qwerty123" not in state
    assert "ghp_" not in state
    assert "[REDACTED_IP]" in state
    assert "[REDACTED_SECRET]" in state


async def test_low_confidence_keeps_the_model_label():
    async def backend(settings, state, usage):
        return LLMClassificationOutput(
            function="it_infrastructure", confidence=0.429, reason="low"
        )

    service = ClassificationService(Settings(_env_file=None), backend=backend)
    response = await service.classify("деплой упал помогите")
    assert response.status is ResponseStatus.classified
    assert response.decision == "it_infrastructure"
    assert response.classification is not None
    assert response.classification.confidence == 0.429


async def test_missing_url_is_not_a_decision():
    service = ClassificationService(Settings(_env_file=None))
    response = await service.classify("Не работает VPN")
    assert response.status is ResponseStatus.failed
    assert response.classification is None
    assert response.errors[0]["code"] == "not_configured"


async def test_elapsed_budget_returns_timeout_without_calling_joey():
    called = False

    async def backend(settings, state, usage):
        nonlocal called
        called = True
        return LLMClassificationOutput(function="network", confidence=0.9, reason="x")

    service = ClassificationService(
        Settings(_env_file=None, request_timeout_seconds=5),
        backend=backend,
    )
    response = await service.classify("vpn", started_at=time.perf_counter() - 30)
    assert response.errors[0] == {
        "code": "timeout",
        "message": "Request processing timed out",
    }
    assert called is False


async def test_joey_http_error_hides_the_response_body(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="model missing sk-live secret")

    monkeypatch.setattr(
        joey_systemone.httpx,
        "AsyncClient",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )
    reset_shared_client()
    service = ClassificationService(
        Settings(
            _env_file=None,
            JOEY_SYSTEMONE_URL="http://joey.test/v1/systemone",
            JOEY_TIMEOUT_SECONDS=2,
        )
    )
    response = await service.classify("Не работает VPN")
    assert response.status is ResponseStatus.failed
    assert response.classification is None
    assert response.errors[0]["code"] == "classification_error"
    assert response.errors[0]["message"] == "Classification failed"
    assert "sk-live" not in response.errors[0]["message"]
