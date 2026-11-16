from pathlib import Path

from app.core.security import EXTENSION_TO_CATEGORY
from app.llm.client import LLMUsageTracker, OpenAIClassificationClient
from app.parsers.base import BaseParser, ParserKind
from app.parsers.documents import DoclingDocumentParser, SpreadsheetParser
from app.parsers.images import ImageParser
from app.parsers.text import CsvParser, StructuredTextParser, TextParser
from app.parsers.visio import VisioParser


def category_for_filename(filename: str) -> str | None:
    ext = Path(filename).suffix.lstrip(".").lower()
    return EXTENSION_TO_CATEGORY.get(ext)


def select_parser(
    filename: str,
    llm_client: OpenAIClassificationClient,
    usage: LLMUsageTracker,
) -> BaseParser | None:
    ext = Path(filename).suffix.lstrip(".").lower()
    category = EXTENSION_TO_CATEGORY.get(ext)
    if not category:
        return None

    if category == "text":
        return TextParser()
    if category == "structured":
        return StructuredTextParser()
    if category == "spreadsheet" and ext == "csv":
        return CsvParser()
    if category == "spreadsheet":
        return SpreadsheetParser()
    if category == "document":
        return DoclingDocumentParser()
    if category == "presentation":
        return DoclingDocumentParser()
    if category == "diagram":
        return VisioParser()
    if category == "image":
        parser = ImageParser(llm_client)
        parser.bind_usage(usage)
        return parser
    return None


def parser_kind_for_file(filename: str) -> ParserKind | None:
    ext = Path(filename).suffix.lstrip(".").lower()
    category = EXTENSION_TO_CATEGORY.get(ext)
    mapping = {
        "text": ParserKind.text,
        "structured": ParserKind.structured,
        "spreadsheet": ParserKind.spreadsheet,
        "document": ParserKind.document,
        "presentation": ParserKind.document,
        "diagram": ParserKind.diagram,
        "image": ParserKind.image,
    }
    return mapping.get(category or "")