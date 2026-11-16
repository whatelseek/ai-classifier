"""Office and spreadsheet parsers using Docling and openpyxl."""

import asyncio
import logging
import tempfile
from pathlib import Path

import httpx
from openpyxl import load_workbook

from app.core.config import get_settings
from app.core.errors import ARCHIVE_TOO_LARGE, EXTRACTION_FAILED, INVALID_ARCHIVE
from app.core.security import (
    ZIP_EXTENSIONS,
    UnsafeArchiveError,
    assert_zip_archive_safe,
    sanitize_for_llm,
)
from app.parsers.base import BaseParser, ParseResult, ParserKind

logger = logging.getLogger(__name__)

# Legacy formats handled by explicit conversion adapters (no macro execution)
LEGACY_EXTENSIONS = frozenset({"doc", "xls", "ppt", "vsd"})


class DoclingDocumentParser(BaseParser):
    """Extracts markdown from PDF and modern Office formats via Docling."""

    kind = ParserKind.document

    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        """Run Docling in a worker thread and cap extracted text length."""
        ext = Path(filename).suffix.lstrip(".").lower()
        if ext in LEGACY_EXTENSIONS:
            return await LegacyConversionAdapter().parse(filename, data, content_type)

        if ext in ZIP_EXTENSIONS:
            archive_error = _zip_guard_error(data)
            if archive_error:
                return ParseResult(
                    filename=filename,
                    parser="docling",
                    status="failed",
                    error=archive_error,
                )

        try:
            settings = get_settings()
            if settings.docling_api_url:
                text = await _docling_extract_remote(
                    filename,
                    data,
                    settings.docling_api_url,
                    settings.docling_timeout_seconds,
                )
            else:
                text = await asyncio.to_thread(_docling_extract, filename, data)
            if not text.strip():
                return ParseResult(
                    filename=filename,
                    parser="docling",
                    status="failed",
                    error="No text extracted from document",
                )
            return ParseResult(
                filename=filename,
                parser="docling",
                status="processed",
                text=sanitize_for_llm(text[:100_000]),
                source_ref=filename,
            )
        except Exception:
            logger.exception("Docling extraction failed for %s", filename)
            return ParseResult(
                filename=filename,
                parser="docling",
                status="failed",
                error=EXTRACTION_FAILED,
            )


async def _docling_extract_remote(
    filename: str,
    data: bytes,
    base_url: str,
    timeout_seconds: int,
) -> str:
    url = f"{base_url.rstrip('/')}/v1/extract"
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, files={"file": (filename, data)})
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("text", ""))


def _docling_extract(filename: str, data: bytes) -> str:
    """Blocking Docling conversion helper executed in ``asyncio.to_thread``."""
    from docling.document_converter import DocumentConverter

    ext = Path(filename).suffix
    with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        converter = DocumentConverter()
        result = converter.convert(tmp.name)
        return result.document.export_to_markdown()


class SpreadsheetParser(BaseParser):
    """Reads XLSX workbooks with openpyxl."""

    kind = ParserKind.spreadsheet

    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        """Extract a bounded preview of sheet rows."""
        ext = Path(filename).suffix.lstrip(".").lower()
        if ext == "xls":
            return await LegacyConversionAdapter().parse(filename, data, content_type)
        if ext in ZIP_EXTENSIONS:
            archive_error = _zip_guard_error(data)
            if archive_error:
                return ParseResult(
                    filename=filename,
                    parser="openpyxl",
                    status="failed",
                    error=archive_error,
                )
        try:
            text = await asyncio.to_thread(_openpyxl_extract, data)
            return ParseResult(
                filename=filename,
                parser="openpyxl",
                status="processed",
                text=sanitize_for_llm(text),
                source_ref=filename,
            )
        except Exception:
            logger.exception("Spreadsheet extraction failed for %s", filename)
            return ParseResult(
                filename=filename,
                parser="openpyxl",
                status="failed",
                error=EXTRACTION_FAILED,
            )


def _zip_guard_error(data: bytes) -> str | None:
    """Return a client-safe message when a ZIP payload is unsafe.

    Args:
        data: Raw upload bytes.

    Returns:
        A stable error string, or ``None`` when the archive is within limits.
    """
    try:
        assert_zip_archive_safe(data)
    except UnsafeArchiveError:
        logger.warning("Rejected archive that exceeds the decompression limit")
        return ARCHIVE_TOO_LARGE
    except ValueError:
        logger.warning("Rejected upload that is not a valid ZIP archive")
        return INVALID_ARCHIVE
    return None


def _openpyxl_extract(data: bytes) -> str:
    from io import BytesIO

    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    parts: list[str] = []
    for sheet in wb.worksheets[:10]:
        parts.append(f"## Sheet: {sheet.title}")
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i > 200:
                break
            cells = ["" if c is None else str(c) for c in row]
            parts.append("\t".join(cells))
    wb.close()
    return "\n".join(parts)[:100_000]


class LegacyConversionAdapter(BaseParser):
    """Fails fast for legacy Office/Visio binaries requiring external conversion."""

    kind = ParserKind.conversion

    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        """Return an explicit error instructing users to upload modern formats."""
        ext = Path(filename).suffix.lstrip(".").lower()
        return ParseResult(
            filename=filename,
            parser=f"{ext}_conversion_adapter",
            status="failed",
            error=(
                f"Legacy .{ext} format requires external conversion; "
                "not available in MVP. Re-upload as modern equivalent (e.g. docx, xlsx)."
            ),
        )