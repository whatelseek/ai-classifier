"""HTTP API: the same decision for every way of sending a description."""

import asyncio
import io

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_app_settings, get_request_semaphore, get_service
from app.core.config import Settings
from app.llm.schemas import LLMClassificationOutput
from app.main import create_app
from app.services.classifier import ClassificationService


async def keyword_backend(settings, state, usage):
    usage.llm_calls += 1
    usage.token_usage["input"] += 12
    usage.token_usage["output"] += 1
    usage.token_usage["total"] += 13
    text = state.lower()
    if any(word in text for word in ("vpn", "ipsec", "check point")):
        function = "network"
    elif "postgres" in text:
        function = "database"
    else:
        function = "needs_review"
    return LLMClassificationOutput(function=function, confidence=0.9, reason="keyword")


@pytest.fixture
def app():
    application = create_app()
    application.dependency_overrides[get_service] = lambda: ClassificationService(
        Settings(_env_file=None, JOEY_SYSTEMONE_URL="http://joey.test/v1/systemone"),
        backend=keyword_backend,
    )
    return application


@pytest.mark.asyncio
async def test_health_ready_functions(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/health")).json()["status"] == "ok"
        ready = (await client.get("/ready")).json()
        assert ready["status"] == "ready"
        assert "joey_uses_systemone" in ready
        assert ready["joey_decision_model"]
        funcs = await client.get("/api/v1/functions")
        codes = {item["code"] for item in funcs.json()["functions"]}
        assert codes == {"database", "security", "network", "it_infrastructure"}


@pytest.mark.asyncio
async def test_classify_and_score_return_the_same_decision(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        classify = await client.post(
            "/api/v1/classify",
            data={"description": "IPsec VPN tunnel is not working with Check Point"},
        )
        score = await client.post(
            "/api/v1/score",
            data={"description": "IPsec VPN tunnel is not working with Check Point"},
        )
    assert classify.status_code == 200
    body = classify.json()
    assert body["status"] == "classified"
    assert body["decision"] == "network"
    assert body["classification"]["function"] == "network"
    assert body["attachments"] == []
    assert body["processing"]["llm_calls"] == 1
    assert score.json()["decision"] == body["decision"]
    assert score.json()["classification"]["confidence"] == body["classification"]["confidence"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"json": {"description": "IPsec VPN tunnel is not working with Check Point"}}, "network"),
        ({"data": {"description": "PostgreSQL replication is broken"}}, "database"),
        (
            {"content": "Please help with computer", "headers": {"content-type": "text/plain"}},
            "unclassified",
        ),
    ],
)
async def test_decide_endpoint(app, kwargs, expected):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/decide", **kwargs)
    assert resp.status_code == 200
    assert resp.json()["decision"] == expected


@pytest.mark.asyncio
async def test_decide_requires_description(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/v1/decide", json={})).status_code == 422
        assert (await client.post("/api/v1/classify", data={})).status_code == 422


@pytest.mark.asyncio
async def test_attachments_are_rejected(app):
    transport = ASGITransport(app=app)
    files = {"files": ("note.txt", io.BytesIO(b"see ticket"), "text/plain")}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/classify",
            data={"description": "деплой упал помогите"},
            files=files,
        )
    assert resp.status_code == 422
    assert "Attachments" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_decide_reports_a_model_failure():
    async def boom(settings, state, usage):
        raise RuntimeError("secret sk-live /tmp/openai-key")

    application = create_app()
    application.dependency_overrides[get_app_settings] = lambda: Settings(
        _env_file=None,
        JOEY_SYSTEMONE_URL="http://joey.test/v1/systemone",
        request_timeout_seconds=5,
    )
    application.dependency_overrides[get_service] = lambda: ClassificationService(
        Settings(_env_file=None, JOEY_SYSTEMONE_URL="http://joey.test/v1/systemone"),
        backend=boom,
    )
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        decide = await client.post("/api/v1/decide", json={"description": "VPN down"})
        classify = await client.post("/api/v1/classify", data={"description": "VPN down"})
    assert decide.status_code == 502
    assert "sk-live" not in decide.text
    assert "secret" not in decide.text
    assert "openai-key" not in decide.text
    body = classify.json()
    assert body["status"] == "failed"
    assert body["errors"][0]["code"] == "classification_error"
    assert "sk-live" not in body["errors"][0]["message"]


@pytest.mark.asyncio
async def test_queue_wait_counts_toward_request_timeout(app):
    app.dependency_overrides[get_app_settings] = lambda: Settings(
        _env_file=None,
        request_timeout_seconds=1,
        JOEY_SYSTEMONE_URL="http://joey.test/v1/systemone",
    )
    app.dependency_overrides[get_request_semaphore] = lambda: asyncio.Semaphore(0)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/classify", data={"description": "IPsec VPN tunnel"})
    body = resp.json()
    assert body["status"] == "failed"
    assert body["errors"][0]["code"] == "timeout"
    assert "Traceback" not in body["errors"][0]["message"]


@pytest.mark.asyncio
async def test_concurrent_requests_keep_separate_results(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        network, database = await asyncio.gather(
            client.post("/api/v1/classify", data={"description": "IPsec VPN tunnel is not working"}),
            client.post("/api/v1/classify", data={"description": "PostgreSQL replication is broken"}),
        )
    assert network.json()["decision"] == "network"
    assert database.json()["decision"] == "database"
    assert network.json()["request_id"] != database.json()["request_id"]


@pytest.mark.asyncio
async def test_openapi_has_no_scoring_only_parameter(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        schema = (await client.get("/openapi.json")).json()
    for path in ("/api/v1/classify", "/api/v1/score"):
        params = schema["paths"][path]["post"].get("parameters") or []
        assert "scoring_only" not in {item["name"] for item in params}
