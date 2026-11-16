import asyncio
import io
import zipfile
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring as safe_fromstring

from app.core.security import sanitize_for_llm
from app.parsers.base import BaseParser, ParseResult, ParserKind
from app.parsers.documents import LegacyConversionAdapter


class VisioParser(BaseParser):
    kind = ParserKind.diagram

    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
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
        except Exception as exc:
            return ParseResult(
                filename=filename,
                parser="vsdx",
                status="failed",
                error=str(exc),
            )


def _parse_vsdx(data: bytes) -> tuple[str, dict]:
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError("Invalid VSDX: not a ZIP archive")

    shapes: list[str] = []
    connectors: list[str] = []
    pages: list[str] = []

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # Guard against zip bombs
        total_uncompressed = sum(i.file_size for i in zf.infolist())
        if total_uncompressed > 100 * 1024 * 1024:
            raise ValueError("VSDX exceeds safe decompression limit")

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