"""Minimal HTTP API for Docling document extraction on Spark."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI(title="Docling Extract Service", version="0.1.0")


class ExtractResponse(BaseModel):
    text: str
    filename: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/extract", response_model=ExtractResponse)
async def extract(file: UploadFile = File(...)) -> ExtractResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    from docling.document_converter import DocumentConverter

    ext = Path(file.filename).suffix or ".bin"
    text = await _convert(data, ext)
    if not text.strip():
        raise HTTPException(status_code=422, detail="no text extracted")
    return ExtractResponse(text=text[:100_000], filename=file.filename)


async def _convert(data: bytes, suffix: str) -> str:
    import asyncio

    return await asyncio.to_thread(_convert_sync, data, suffix)


def _convert_sync(data: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        converter = DocumentConverter()
        result = converter.convert(tmp.name)
        return result.document.export_to_markdown()