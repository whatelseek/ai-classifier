from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class ParserKind(str, Enum):
    text = "text"
    document = "document"
    image = "image"
    diagram = "diagram"
    spreadsheet = "spreadsheet"
    structured = "structured"
    conversion = "conversion"


@dataclass(slots=True)
class ParseResult:
    filename: str
    parser: str
    status: str  # processed | failed
    text: str = ""
    metadata: dict | None = None
    error: str | None = None
    source_ref: str | None = None


class BaseParser(ABC):
    kind: ParserKind

    @abstractmethod
    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        pass