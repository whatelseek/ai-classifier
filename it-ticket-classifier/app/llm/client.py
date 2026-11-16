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
    llm_calls: int = 0
    token_usage: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0, "total": 0})

    def record(self, usage: Any | None) -> None:
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
    def __init__(self, settings: Settings) -> None:
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
        return self._client is not None

    async def classify(
        self,
        description: str,
        merged_context: str,
        client: str | None,
        issue_key: str | None,
        usage: LLMUsageTracker,
    ) -> LLMClassificationOutput:
        if not self._client:
            raise RuntimeError("OpenAI API key is not configured")

        user_content = build_classification_user_content(
            description, merged_context, client, issue_key
        )
        # Truncate to approximate token budget (chars / 4 heuristic)
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
        data = json.loads(text)
        return LLMClassificationOutput.model_validate(data)

    async def analyze_image(
        self,
        image_bytes: bytes,
        media_type: str,
        prompt: str,
        usage: LLMUsageTracker,
    ) -> str:
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
    # Responses API: aggregate output_text or walk output items
    if hasattr(response, "output_text") and response.output_text:
        return str(response.output_text)
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            if getattr(content, "type", None) == "output_text":
                chunks.append(getattr(content, "text", "") or "")
    return "".join(chunks)