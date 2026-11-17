"""Abstract parser interface and shared result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class ParserKind(str, Enum):
    """High-level parser family used for routing and telemetry."""

    text = "text"
    document = "document"
    image = "image"
    diagram = "diagram"
    spreadsheet = "spreadsheet"
    structured = "structured"
    conversion = "conversion"


@dataclass(slots=True)
class ParseResult:
    """Outcome of parsing a single attachment.

    Attributes:
        filename: Original filename.
        parser: Implementation name reported to clients.
        status: ``processed`` or ``failed``.
        text: Extracted text when successful.
        metadata: Optional structured details (e.g. diagram counts).
        error: Human-readable failure reason.
        source_ref: Citation id used during context merge.
    """

    filename: str
    parser: str
    status: str
    text: str = ""
    metadata: dict | None = None
    error: str | None = None
    source_ref: str | None = None


class BaseParser(ABC):
    """Async parser contract implemented by each format handler."""

    kind: ParserKind

    @abstractmethod
    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        """Extract text or structured content from raw bytes.

        Args:
            filename: Original filename including extension.
            data: Full file contents.
            content_type: Optional MIME type from the upload.

        Returns:
            ParseResult describing success or explicit failure.
        """
        raise NotImplementedError