"""Office and spreadsheet parsers using Docling and openpyxl."""

import asyncio
import logging
import tempfile
from pathlib import Path

from openpyxl import load_workbook

from app.core.security import sanitize_for_llm
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

        try:
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
        except Exception as exc:
            logger.exception("Docling extraction failed for %s", filename)
            return ParseResult(
                filename=filename,
                parser="docling",
                status="failed",
                error=str(exc),
            )


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
        try:
            text = await asyncio.to_thread(_openpyxl_extract, data)
            return ParseResult(
                filename=filename,
                parser="openpyxl",
                status="processed",
                text=sanitize_for_llm(text),
                source_ref=filename,
            )
        except Exception as exc:
            return ParseResult(
                filename=filename,
                parser="openpyxl",
                status="failed",
                error=str(exc),
            )


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