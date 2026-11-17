"""Raster image parser using vision-capable LLMs."""

import logging

from app.core.config import get_settings
from app.core.errors import EXTRACTION_FAILED
from app.core.security import sanitize_for_llm
from app.llm.client import LLMUsageTracker, OpenAIClassificationClient, is_transient_llm_error
from app.parsers.base import BaseParser, ParseResult, ParserKind

logger = logging.getLogger(__name__)

VISION_PROMPT = (
    "Extract technical details from this IT support screenshot or diagram image. "
    "Include visible error messages, hostnames, service names, and infrastructure hints. "
    "Do not invent content. Do not transcribe passwords, API keys, tokens, or private keys. "
    "Output plain text bullet points."
)

MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


class ImageParser(BaseParser):
    """Sends screenshots to the vision model for OCR-style extraction."""

    kind = ParserKind.image

    def __init__(self, llm_client: OpenAIClassificationClient | None = None) -> None:
        """Optionally inject a shared LLM client for vision calls."""
        self._llm = llm_client or OpenAIClassificationClient(get_settings())
        self._usage: LLMUsageTracker | None = None

    def bind_usage(self, usage: LLMUsageTracker) -> None:
        """Attach a request-scoped usage tracker for token accounting."""
        self._usage = usage

    async def parse(self, filename: str, data: bytes, content_type: str | None) -> ParseResult:
        """Analyze image bytes and return bullet-point technical notes."""
        ext = filename.rsplit(".", 1)[-1].lower()
        media = MEDIA_TYPES.get(ext, content_type or "image/png")

        settings = get_settings()
        if settings.classification_scoring_only:
            return ParseResult(
                filename=filename,
                parser="image",
                status="skipped",
                error="Vision LLM disabled in classification scoring-only mode",
            )

        if not self._llm.is_available:
            return ParseResult(
                filename=filename,
                parser="image",
                status="failed",
                error="OpenAI API key not configured; cannot analyze image",
            )

        usage = self._usage or LLMUsageTracker()
        try:
            text = sanitize_for_llm(await self._llm.analyze_image(data, media, VISION_PROMPT, usage))
            if not text.strip():
                return ParseResult(
                    filename=filename,
                    parser="openai_vision",
                    status="failed",
                    error="Vision model returned empty analysis",
                )
            return ParseResult(
                filename=filename,
                parser="openai_vision",
                status="processed",
                text=text,
                source_ref=filename,
            )
        except Exception as exc:
            if is_transient_llm_error(exc):
                raise
            logger.exception("Vision analysis failed for %s", filename)
            return ParseResult(
                filename=filename,
                parser="openai_vision",
                status="failed",
                error=EXTRACTION_FAILED,
            )