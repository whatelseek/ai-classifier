"""Plain text, CSV, and structured text (JSON/XML/YAML) parsers."""

import csv
import io
import json
import logging

import yaml

from app.core.errors import EXTRACTION_FAILED
from app.core.security import sanitize_for_llm
from app.parsers.base import BaseParser, ParseResult, ParserKind

logger = logging.getLogger(__name__)


class TextParser(BaseParser):
    """Decodes UTF-8 log and text files."""

    kind = ParserKind.text

    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        """Decode bytes as UTF-8 text with replacement on errors."""
        try:
            text = data.decode("utf-8", errors="replace")
            text = sanitize_for_llm(text)
            return ParseResult(
                filename=filename,
                parser="text",
                status="processed",
                text=text,
                source_ref=filename,
            )
        except Exception:
            logger.exception("Text extraction failed for %s", filename)
            return ParseResult(
                filename=filename,
                parser="text",
                status="failed",
                error=EXTRACTION_FAILED,
            )


class StructuredTextParser(BaseParser):
    """Parses JSON, YAML, and generic XML-like text."""

    kind = ParserKind.structured

    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        """Normalize structured text into a string for the LLM."""
        ext = filename.rsplit(".", 1)[-1].lower()
        try:
            raw = data.decode("utf-8", errors="replace")
            if ext == "json":
                obj = json.loads(raw)
                text = sanitize_for_llm(json.dumps(obj, indent=2)[:50000])
                parser_name = "json"
            elif ext in ("yaml", "yml"):
                obj = yaml.safe_load(raw)
                text = sanitize_for_llm(yaml.safe_dump(obj)[:50000])
                parser_name = "yaml"
            else:
                text = sanitize_for_llm(raw)
                parser_name = "xml"
            return ParseResult(
                filename=filename,
                parser=parser_name,
                status="processed",
                text=text,
                source_ref=filename,
            )
        except Exception:
            logger.exception("Structured extraction failed for %s", filename)
            return ParseResult(
                filename=filename,
                parser="structured",
                status="failed",
                error=EXTRACTION_FAILED,
            )


class CsvParser(BaseParser):
    """Reads delimiter-separated rows from CSV uploads."""

    kind = ParserKind.spreadsheet

    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        """Parse up to 500 CSV rows into tabular text."""
        try:
            raw = data.decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(raw))
            rows = list(reader)[:500]
            text = "\n".join(",".join(row) for row in rows)
            text = sanitize_for_llm(text)
            return ParseResult(
                filename=filename,
                parser="csv",
                status="processed",
                text=text,
                source_ref=filename,
            )
        except Exception:
            logger.exception("CSV extraction failed for %s", filename)
            return ParseResult(
                filename=filename,
                parser="csv",
                status="failed",
                error=EXTRACTION_FAILED,
            )