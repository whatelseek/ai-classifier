"""OpenAI Responses API client for classification and vision inference."""

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from app.core.config import Settings
from app.llm.prompts import CLASSIFICATION_SYSTEM_PROMPT, build_classification_user_content
from app.llm.prompts_joey import JOEY_CLASSIFICATION_SYSTEM_PROMPT, build_joey_user_content
from app.llm.schemas import (
    CLASSIFICATION_JSON_SCHEMA,
    JOEY_CLASSIFICATION_JSON_SCHEMA,
    LLMClassificationOutput,
)
from app.llm.joey_hints import adjust_joey_classification
from app.llm.ticket_body import extract_request_body

logger = logging.getLogger(__name__)

# Transient Responses API failures. LangGraph RetryPolicy retries these;
# the SDK client itself does not, so a node attempt is one HTTP call.
TRANSIENT_LLM_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)


def is_transient_llm_error(exc: BaseException) -> bool:
    """Return True when an exception is a retryable OpenAI transport failure.

    Args:
        exc: Exception raised by the OpenAI SDK or a wrapper.

    Returns:
        True for connection, timeout, rate-limit, and 5xx errors.
    """
    return isinstance(exc, TRANSIENT_LLM_ERRORS)


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
        inp = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0) or 0
        out = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", 0) or 0
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
        self._use_chat_api = settings.uses_openai_compatible_proxy
        if settings.openai_configured:
            api_key = (settings.openai_api_key or "dummy").strip() or "dummy"
            # Retries are owned by the LangGraph RetryPolicy on LLM nodes so
            # only the failing branch is repeated.
            kwargs: dict[str, Any] = {
                "api_key": api_key,
                "timeout": settings.openai_timeout_seconds,
                "max_retries": 0,
            }
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url.rstrip("/")
            # Envoy AI Gateway picks the Spark backend via x-ai-eg-model (Joey/Qwen routes).
            if settings.openai_base_url and settings.openai_text_model:
                kwargs["default_headers"] = {"x-ai-eg-model": settings.openai_text_model}
            self._client = AsyncOpenAI(**kwargs)

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
        retry_feedback: str | None = None,
    ) -> LLMClassificationOutput:
        """Run structured classification over description and merged attachment text.

        Uses ``responses.parse`` so the SDK sends a strict JSON schema
        (``additionalProperties: false`` and every property required).

        Args:
            description: Ticket body.
            merged_context: Parsed attachment content.
            client: Optional client name for the prompt.
            issue_key: Optional ticket id for the prompt.
            usage: Mutable tracker updated with token counts.
            retry_feedback: Optional note that makes a retry prompt differ
                from the previous attempt.

        Returns:
            Validated ``LLMClassificationOutput``.

        Raises:
            RuntimeError: When no API key is configured.
            TypeError: When the model returns an empty parsed payload.
        """
        if not self._client:
            raise RuntimeError("OpenAI API key is not configured")

        body = description
        if self._settings.classify_extract_request_body:
            body = extract_request_body(description)

        use_joey = "joey" in (self._settings.openai_text_model or "").lower()
        if use_joey:
            system_prompt = JOEY_CLASSIFICATION_SYSTEM_PROMPT
            user_content = build_joey_user_content(
                body, merged_context, retry_feedback=retry_feedback
            )
            json_schema = JOEY_CLASSIFICATION_JSON_SCHEMA
            strict_json = False
        else:
            system_prompt = CLASSIFICATION_SYSTEM_PROMPT
            user_content = build_classification_user_content(
                body,
                merged_context,
                client,
                issue_key,
                retry_feedback=retry_feedback,
                max_chars=self._settings.openai_max_input_tokens * 4,
            )
            json_schema = CLASSIFICATION_JSON_SCHEMA
            strict_json = True

        if self._use_chat_api:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_text_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ticket_classification",
                        "strict": strict_json,
                        "schema": json_schema,
                    },
                },
                max_tokens=self._settings.openai_max_output_tokens,
                temperature=0.0,
            )
            usage.record(response.usage)
            raw = (response.choices[0].message.content or "").strip()
            if not raw:
                raise TypeError("Empty model response")
            parsed = _parse_classification_json(raw)
            if use_joey:
                parsed = adjust_joey_classification(body, parsed)
        else:
            response = await self._client.responses.parse(
                model=self._settings.openai_text_model,
                input=[
                    {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                text_format=LLMClassificationOutput,
            )
            usage.record(response.usage)
            parsed = response.output_parsed
        if not isinstance(parsed, LLMClassificationOutput):
            raise TypeError("Empty model response")
        return parsed

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

        if self._use_chat_api:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
            usage.record(response.usage)
            return (response.choices[0].message.content or "").strip()
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


def _normalize_vllm_structured_json(raw: str) -> str:
    """Repair Joey/vLLM structured outputs that pad with tabs after ``confidence``."""
    text = raw.strip()
    func_match = re.search(
        r'"function"\s*:\s*"(?P<func>network|linux|security|database|needs_review)"',
        text,
        flags=re.IGNORECASE,
    )
    if not func_match:
        return re.sub(r"[\t ]{20,}", "", text)
    func = func_match.group("func").lower()
    conf_match = re.search(r'"confidence"\s*:\s*(?P<c>0(?:\.\d+)?|1(?:\.0+)?)', text)
    has_padding = re.search(r'"confidence"\s*:\s*[\t ]{2,}', text) is not None
    try_to_repair = has_padding or (
        conf_match is None and re.search(r'"confidence"\s*:', text) is not None
    )
    if try_to_repair:
        confidence = float(conf_match.group("c")) if conf_match else 0.72
        return json.dumps(
            {
                "function": func,
                "confidence": confidence,
                "reason": "Structured model head (vLLM output padding removed)",
                "alternatives": [],
                "evidence": [],
            }
        )
    return re.sub(r"[\t ]{20,}", "", text)


def _parse_classification_json(raw: str) -> LLMClassificationOutput:
    """Parse model JSON, tolerating trailing junk from smaller local models."""
    raw = _normalize_vllm_structured_json(raw)
    try:
        return LLMClassificationOutput.model_validate_json(raw)
    except ValueError:
        salvaged = _salvage_classification_json(raw)
        if salvaged is not None:
            return salvaged
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise
        snippet = match.group(0)
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", snippet)
        try:
            return LLMClassificationOutput.model_validate(json.loads(cleaned))
        except (ValueError, json.JSONDecodeError):
            salvaged = _salvage_classification_json(cleaned)
            if salvaged is not None:
                return salvaged
            raise


def _salvage_classification_json(raw: str) -> LLMClassificationOutput | None:
    """Recover classification when vLLM returns truncated JSON."""
    func_match = re.search(
        r'"function"\s*:\s*"(?P<func>network|linux|security|database|needs_review)"',
        raw,
        re.IGNORECASE,
    )
    if not func_match:
        return None
    func = func_match.group("func").lower()
    confidence = 0.65
    conf_match = re.search(r'"confidence"\s*:\s*(?P<c>-?\d+(?:\.\d+)?)', raw)
    if conf_match:
        parsed_conf = float(conf_match.group("c"))
        confidence = parsed_conf if 0.0 <= parsed_conf <= 1.0 else 0.72
    reason = "Recovered from partial model JSON (truncated or padded structured output)"
    reason_match = re.search(r'"reason"\s*:\s*"(?P<r>(?:\\.|[^"\\])*)"', raw, re.DOTALL)
    if reason_match:
        reason = reason_match.group("r").replace('\\"', '"')[:2000]
    return LLMClassificationOutput(
        function=func,  # type: ignore[arg-type]
        confidence=confidence,
        reason=reason,
        alternatives=[],
        evidence=[],
    )


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