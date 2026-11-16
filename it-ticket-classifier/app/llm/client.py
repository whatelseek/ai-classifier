"""OpenAI Responses API client for classification and vision inference."""

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from app.core.config import Settings
from app.llm.prompts import CLASSIFICATION_SYSTEM_PROMPT, build_classification_user_content
from app.llm.schemas import CLASSIFICATION_JSON_SCHEMA, LLMClassificationOutput

logger = logging.getLogger(__name__)


@dataclass
class LLMUsageTracker:
    """Accumulates per-request LLM call counts and token usage."""

    llm_calls: int = 0
    token_usage: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0, "total": 0})

    def record(self, usage: Any | None) -> None:
        """Increment counters from an OpenAI Responses usage object.

        Args:
            usage: Usage block from a Responses API response.
        """
        self.llm_calls += 1
        if usage is None:
            return
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        total = getattr(usage, "total_tokens", inp + out) or (inp + out)
        self.token_usage["input"] += inp
        self.token_usage["output"] += out
        self.token_usage["total"] += total


class OpenAIClassificationClient:
    """Thin wrapper around AsyncOpenAI for structured ticket classification."""

    def __init__(self, settings: Settings) -> None:
        """Create a client when an API key is configured.

        Args:
            settings: OpenAI credentials, models, and timeouts.
        """
        self._settings = settings
        self._client: AsyncOpenAI | None = None
        if settings.openai_configured:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
            )

    @property
    def is_available(self) -> bool:
        """Return True when the underlying HTTP client was constructed."""
        return self._client is not None

    async def classify(
        self,
        description: str,
        merged_context: str,
        client: str | None,
        issue_key: str | None,
        usage: LLMUsageTracker,
    ) -> LLMClassificationOutput:
        """Run structured classification over description and merged attachment text.

        Args:
            description: Ticket body.
            merged_context: Parsed attachment content.
            client: Optional client name for the prompt.
            issue_key: Optional ticket id for the prompt.
            usage: Mutable tracker updated with token counts.

        Returns:
            Validated ``LLMClassificationOutput``.

        Raises:
            RuntimeError: When no API key is configured.
            ValueError: When the model returns empty or invalid JSON.
        """
        if not self._client:
            raise RuntimeError("OpenAI API key is not configured")

        user_content = build_classification_user_content(
            description, merged_context, client, issue_key
        )
        max_chars = self._settings.openai_max_input_tokens * 4
        if len(user_content) > max_chars:
            user_content = user_content[:max_chars] + "\n...[truncated]"

        response = await self._client.responses.create(
            model=self._settings.openai_text_model,
            input=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ticket_classification",
                    "schema": CLASSIFICATION_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        usage.record(response.usage)

        text = _extract_output_text(response)
        if not text:
            raise ValueError("Empty model response")
        return LLMClassificationOutput.model_validate(json.loads(text))

    async def analyze_image(
        self,
        image_bytes: bytes,
        media_type: str,
        prompt: str,
        usage: LLMUsageTracker,
    ) -> str:
        """Extract textual technical details from a screenshot or diagram image.

        Args:
            image_bytes: Raw image file contents.
            media_type: MIME type for the data URL.
            prompt: Vision instruction prompt.
            usage: Mutable LLM usage tracker.

        Returns:
            Model-generated plain text summary.

        Raises:
            RuntimeError: When no API key is configured.
        """
        if not self._client:
            raise RuntimeError("OpenAI API key is not configured")

        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        data_url = f"data:{media_type};base64,{b64}"

        response = await self._client.responses.create(
            model=self._settings.openai_vision_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
        )
        usage.record(response.usage)
        return _extract_output_text(response) or ""


def _extract_output_text(response: Any) -> str:
    """Aggregate text segments from a Responses API payload.

    Args:
        response: Raw Responses API result object.

    Returns:
        Concatenated assistant output text, or an empty string.
    """
    if hasattr(response, "output_text") and response.output_text:
        return str(response.output_text)
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            if getattr(content, "type", None) == "output_text":
                chunks.append(getattr(content, "text", "") or "")
    return "".join(chunks)