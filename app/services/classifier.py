"""Classify one ticket description with Joey."""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from app.core.config import Settings, get_settings
from app.core.errors import CLASSIFICATION_FAILED, NOT_CONFIGURED, REQUEST_TIMEOUT
from app.core.logging import request_id_var
from app.core.security import sanitize_for_llm
from app.llm.joey_systemone import LLMUsageTracker, classify_via_systemone
from app.llm.schemas import LLMClassificationOutput
from app.llm.ticket_body import extract_request_body
from app.models.responses import (
    AlternativeFunction,
    ClassificationResult,
    ClassifyResponse,
    ProcessingMeta,
    ResponseStatus,
)

logger = logging.getLogger(__name__)

ClassifyBackend = Callable[[Settings, str, LLMUsageTracker], Awaitable[LLMClassificationOutput]]


class ClassificationService:
    """Turn a ticket description into one routing decision."""

    def __init__(
        self,
        settings: Settings | None = None,
        backend: ClassifyBackend | None = None,
    ) -> None:
        """Use ``backend`` in tests. Production calls System One."""
        self._settings = settings or get_settings()
        self._backend = backend

    async def classify(self, description: str, started_at: float | None = None) -> ClassifyResponse:
        """Classify ``description``. ``started_at`` counts queue wait toward the deadline."""
        request_id = f"req-{uuid.uuid4().hex[:12]}"
        token = request_id_var.set(request_id)
        start = started_at if started_at is not None else time.perf_counter()
        try:
            remaining = self._settings.request_timeout_seconds - (time.perf_counter() - start)
            if remaining <= 0:
                return self._failed(request_id, start, "timeout", REQUEST_TIMEOUT)

            backend = self._backend
            if backend is None:
                if not self._settings.joey_uses_systemone:
                    return self._failed(request_id, start, "not_configured", NOT_CONFIGURED)
                backend = classify_via_systemone

            # Same text Joey sees, with or without anything else the client attached.
            text = sanitize_for_llm(
                extract_request_body(description, include_attachments=False),
                mask_hosts=self._settings.mask_internal_hosts,
            )
            if not text.strip():
                return self._failed(request_id, start, "validation_error", "description is empty")

            usage = LLMUsageTracker()
            try:
                async with asyncio.timeout(remaining):
                    result = await backend(self._settings, text, usage)
            except TimeoutError:
                return self._failed(request_id, start, "timeout", REQUEST_TIMEOUT)
            except Exception:
                logger.exception("Classification failed")
                return self._failed(request_id, start, "classification_error", CLASSIFICATION_FAILED)

            classification = ClassificationResult(
                function=result.function,
                confidence=result.confidence,
                reason=result.reason,
                alternatives=[
                    AlternativeFunction(function=item.function, score=item.score)
                    for item in result.alternatives
                ],
                evidence=list(result.evidence),
            )
            status = (
                ResponseStatus.needs_review
                if result.function == "needs_review"
                else ResponseStatus.classified
            )
            return ClassifyResponse(
                request_id=request_id,
                status=status,
                classification=classification,
                processing=ProcessingMeta(
                    model=self._settings.joey_decision_model,
                    llm_calls=usage.llm_calls,
                    duration_ms=_duration_ms(start),
                    token_usage=dict(usage.token_usage),
                ),
            )
        finally:
            request_id_var.reset(token)

    def _failed(self, request_id: str, start: float, code: str, message: str) -> ClassifyResponse:
        return ClassifyResponse(
            request_id=request_id,
            status=ResponseStatus.failed,
            errors=[{"code": code, "message": message}],
            processing=ProcessingMeta(duration_ms=_duration_ms(start)),
        )


def _duration_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
