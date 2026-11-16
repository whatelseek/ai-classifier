import io
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


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
async def test_unsupported_extension_reported(app):
    transport = ASGITransport(app=app)
    files = {"files": ("bad.bin", io.BytesIO(b"\x00\x01"), "application/octet-stream")}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/classify", files=files)
        assert resp.json()["status"] == "failed"