"""Integration tests for FastAPI endpoints and multipart classification."""

import asyncio
import io
import time
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_app_settings, get_request_semaphore
from app.core.config import Settings
from app.main import create_app
from app.models.requests import ClassifyRequestPayload
from app.services.classifier import ClassificationService


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_health_ready_functions(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/health")).json()["status"] == "ok"
        ready = await client.get("/ready")
        assert ready.status_code == 200
        funcs = await client.get("/api/v1/functions")
        codes = {f["code"] for f in funcs.json()["functions"]}
        assert codes == {"network", "linux", "security", "database"}


@pytest.mark.asyncio
async def test_classify_text_network(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/classify",
            data={"description": "IPsec VPN tunnel is not working with Check Point"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("classified", "needs_review")
        assert body["classification"]["function"] in ("network", "needs_review")


@pytest.mark.asyncio
async def test_classify_validation_error(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/classify", data={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_classify_log_attachment(app):
    transport = ASGITransport(app=app)
    log_data = b"FATAL: PostgreSQL could not extend file wal\n"
    files = {"files": ("db.log", io.BytesIO(log_data), "text/plain")}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/classify", files=files)
        body = resp.json()
        assert body["attachments"][0]["status"] == "processed"
        assert body["classification"]["function"] in ("database", "needs_review")


@pytest.mark.asyncio
async def test_classify_vsdx(app):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "visio/pages/page1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main">
              <Shapes>
                <Shape ID="1"><Text>Core Switch</Text></Shape>
                <Connect FromSheet="1" ToSheet="2"/>
              </Shapes>
            </PageContents>""",
        )
    buf.seek(0)
    transport = ASGITransport(app=app)
    files = {"files": ("net.vsdx", buf, "application/vnd.ms-visio.drawing")}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/classify",
            data={"description": "Review network diagram"},
            files=files,
        )
        body = resp.json()
        assert body["attachments"][0]["status"] == "processed"
        assert body["attachments"][0]["parser"] == "vsdx"


@pytest.mark.asyncio
async def test_two_log_files_are_both_processed(app):
    transport = ASGITransport(app=app)
    files = [
        ("files", ("a.log", io.BytesIO(b"vpn ipsec checkpoint\n"), "text/plain")),
        ("files", ("b.log", io.BytesIO(b"postgresql replication wal\n"), "text/plain")),
    ]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/classify", files=files)
        body = resp.json()
        names = {item["filename"]: item["status"] for item in body["attachments"]}
        assert names == {"a.log": "processed", "b.log": "processed"}
        assert body["request_id"]


@pytest.mark.asyncio
async def test_concurrent_requests_keep_separate_results(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        network, database = await asyncio.gather(
            client.post(
                "/api/v1/classify",
                data={"description": "IPsec VPN tunnel is not working with Check Point"},
            ),
            client.post(
                "/api/v1/classify",
                data={"description": "PostgreSQL replication is broken"},
            ),
        )
    assert network.json()["classification"]["function"] == "network"
    assert database.json()["classification"]["function"] == "database"
    assert network.json()["request_id"] != database.json()["request_id"]


@pytest.mark.asyncio
async def test_queue_wait_counts_toward_request_timeout(app):
    app.dependency_overrides[get_app_settings] = lambda: Settings(
        request_timeout_seconds=1,
        openai_api_key="",
    )
    app.dependency_overrides[get_request_semaphore] = lambda: asyncio.Semaphore(0)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/classify",
            data={"description": "IPsec VPN tunnel is not working"},
        )
    body = resp.json()
    assert body["status"] == "failed"
    assert body["errors"][0]["code"] == "timeout"
    assert "Traceback" not in body["errors"][0]["message"]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_internal_error_hides_exception_text():
    service = ClassificationService(Settings(openai_api_key="", request_timeout_seconds=30))

    class Boom:
        async def ainvoke(self, *_args, **_kwargs):
            raise RuntimeError("secret /tmp/openai-key sk-live")

    service._graph = Boom()
    response = await service.classify(
        ClassifyRequestPayload(
            description="VPN down",
            issue_key=None,
            client=None,
            attachments=[],
        ),
        started_at=time.perf_counter(),
    )
    assert response.status.value == "failed"
    message = response.errors[0]["message"]
    assert response.errors[0]["code"] == "internal_error"
    assert "secret" not in message
    assert "sk-live" not in message


@pytest.mark.asyncio
async def test_elapsed_budget_returns_timeout_before_the_graph():
    service = ClassificationService(Settings(openai_api_key="", request_timeout_seconds=5))
    response = await service.classify(
        ClassifyRequestPayload(
            description="VPN down",
            issue_key=None,
            client=None,
            attachments=[],
        ),
        started_at=time.perf_counter() - 30,
    )
    assert response.errors[0]["code"] == "timeout"
    assert response.errors[0]["message"] == "Request processing timed out"


@pytest.mark.asyncio
async def test_unsupported_extension_reported(app):
    transport = ASGITransport(app=app)
    files = {"files": ("bad.bin", io.BytesIO(b"\x00\x01"), "application/octet-stream")}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/classify", files=files)
        assert resp.json()["status"] == "failed"