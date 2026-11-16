"""Microsoft Visio VSDX diagram extraction from embedded XML."""

import asyncio
import io
import logging
import zipfile
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring as safe_fromstring

from app.core.errors import ARCHIVE_TOO_LARGE, EXTRACTION_FAILED, INVALID_ARCHIVE
from app.core.security import UnsafeArchiveError, assert_zip_archive_safe, sanitize_for_llm
from app.parsers.base import BaseParser, ParseResult, ParserKind
from app.parsers.documents import LegacyConversionAdapter

logger = logging.getLogger(__name__)


class VisioParser(BaseParser):
    """Parses VSDX OPC packages and extracts shape and connector metadata."""

    kind = ParserKind.diagram

    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        """Extract diagram labels and relationships from VSDX XML."""
        if filename.lower().endswith(".vsd"):
            return await LegacyConversionAdapter().parse(filename, data, content_type)
        try:
            text, meta = await asyncio.to_thread(_parse_vsdx, data)
            if not text.strip():
                return ParseResult(
                    filename=filename,
                    parser="vsdx",
                    status="failed",
                    error="No diagram elements extracted from VSDX",
                )
            return ParseResult(
                filename=filename,
                parser="vsdx",
                status="processed",
                text=sanitize_for_llm(text),
                metadata=meta,
                source_ref=filename,
            )
        except UnsafeArchiveError:
            return ParseResult(
                filename=filename,
                parser="vsdx",
                status="failed",
                error=ARCHIVE_TOO_LARGE,
            )
        except ValueError:
            return ParseResult(
                filename=filename,
                parser="vsdx",
                status="failed",
                error=INVALID_ARCHIVE,
            )
        except Exception:
            logger.exception("VSDX extraction failed for %s", filename)
            return ParseResult(
                filename=filename,
                parser="vsdx",
                status="failed",
                error=EXTRACTION_FAILED,
            )


def _parse_vsdx(data: bytes) -> tuple[str, dict]:
    """Blocking VSDX XML extraction executed in a worker thread."""
    assert_zip_archive_safe(data)

    shapes: list[str] = []
    connectors: list[str] = []
    pages: list[str] = []

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.startswith("visio/pages/page") and name.endswith(".xml"):
                pages.append(name)
                xml_bytes = zf.read(name)
                root = safe_fromstring(xml_bytes)
                ns = _detect_ns(root)
                for shape in root.iter(f"{{{ns}}}Shape"):
                    shape_id = shape.get("ID", "")
                    name_el = shape.find(f"{{{ns}}}Text")
                    label = (name_el.text or "").strip() if name_el is not None else ""
                    master = shape.get("Master", "")
                    shapes.append(f"Shape id={shape_id} master={master} label={label!r}")
                for conn in root.iter(f"{{{ns}}}Connect"):
                    connectors.append(
                        f"Connect from={conn.get('FromSheet','')} "
                        f"from_cell={conn.get('FromCell','')} "
                        f"to={conn.get('ToSheet','')} to_cell={conn.get('ToCell','')}"
                    )

    lines = ["# Visio diagram extract", f"Pages: {len(pages)}"]
    lines.extend(shapes[:500])
    lines.extend(connectors[:500])
    meta = {"page_count": len(pages), "shape_count": len(shapes), "connector_count": len(connectors)}
    return "\n".join(lines), meta


def _detect_ns(root: ET.Element) -> str:
    if root.tag.startswith("{"):
        return root.tag.split("}")[0][1:]
    return "http://schemas.microsoft.com/office/visio/2012/main"