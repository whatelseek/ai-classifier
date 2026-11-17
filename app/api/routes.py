"""HTTP routes: health, the function catalog, and ticket classification."""

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.dependencies import get_app_settings, get_request_semaphore, get_service
from app.core.config import Settings
from app.core.errors import CLASSIFICATION_FAILED, REQUEST_TIMEOUT
from app.models.responses import (
    ClassifyResponse,
    DecideResponse,
    FunctionsListResponse,
    ProcessingMeta,
    ResponseStatus,
    build_functions_response,
)
from app.services.classifier import ClassificationService

router = APIRouter()

_DECIDE_ERROR_STATUS = {"validation_error": 422, "timeout": 504, "not_configured": 503}
_ATTACHMENTS_REJECTED = "Attachments are not classified; send the description only"


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(settings: Settings = Depends(get_app_settings)) -> dict[str, str | bool]:
    """Readiness probe. ``joey_uses_systemone`` is true when the System One URL is set."""
    return {
        "status": "ready",
        "joey_uses_systemone": settings.joey_uses_systemone,
        "joey_decision_model": settings.joey_decision_model,
    }


@router.get("/api/v1/functions", response_model=FunctionsListResponse)
async def list_functions() -> FunctionsListResponse:
    """List the four routable support teams."""
    return build_functions_response()


@router.post("/api/v1/score", response_model=ClassifyResponse)
@router.post("/api/v1/classify", response_model=ClassifyResponse)
async def classify_ticket(
    description: str | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
    settings: Settings = Depends(get_app_settings),
    service: ClassificationService = Depends(get_service),
    semaphore=Depends(get_request_semaphore),
) -> ClassifyResponse:
    """Classify a ticket description. ``/score`` and ``/classify`` are the same call.

    A file part is rejected: attachments are not read, so they cannot change the decision.
    """
    if files:
        raise HTTPException(status_code=422, detail=_ATTACHMENTS_REJECTED)
    if not isinstance(description, str) or not description.strip():
        raise HTTPException(status_code=422, detail="description is required")
    return await _execute(description, settings, service, semaphore)


@router.post("/api/v1/decide", response_model=DecideResponse)
async def decide_ticket(
    request: Request,
    settings: Settings = Depends(get_app_settings),
    service: ClassificationService = Depends(get_service),
    semaphore=Depends(get_request_semaphore),
) -> DecideResponse:
    """Ticket description in, one decision out.

    Accepts JSON ``{"description": "..."}``, a form field ``description``,
    or a ``text/plain`` body. A failure is an HTTP error: this response has no
    status field, so a Joey outage must not look like ``unclassified``.
    """
    description = await _read_description(request)
    response = await _execute(description, settings, service, semaphore)
    if response.status is ResponseStatus.failed or response.classification is None:
        error = response.errors[0] if response.errors else {}
        status_code = _DECIDE_ERROR_STATUS.get(error.get("code", ""), 502)
        raise HTTPException(status_code=status_code, detail=error.get("message", CLASSIFICATION_FAILED))
    return DecideResponse(decision=response.decision, confidence=response.classification.confidence)


async def _read_description(request: Request) -> str:
    content_type = request.headers.get("content-type", "")
    description: object
    if content_type.startswith("application/json"):
        try:
            data = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="description is required") from exc
        description = data.get("description") if isinstance(data, dict) else None
    elif content_type.startswith("multipart/form-data"):
        form = await request.form()
        if any(isinstance(value, UploadFile) for value in form.values()):
            raise HTTPException(status_code=422, detail=_ATTACHMENTS_REJECTED)
        description = form.get("description")
    elif content_type.startswith("application/x-www-form-urlencoded"):
        description = (await request.form()).get("description")
    else:
        description = (await request.body()).decode("utf-8", errors="replace")
    if not isinstance(description, str) or not description.strip():
        raise HTTPException(status_code=422, detail="description is required")
    return description


async def _execute(
    description: str,
    settings: Settings,
    service: ClassificationService,
    semaphore: asyncio.Semaphore,
) -> ClassifyResponse:
    started = time.perf_counter()
    try:
        async with asyncio.timeout(settings.request_timeout_seconds):
            async with semaphore:
                return await service.classify(description, started_at=started)
    except TimeoutError:
        return ClassifyResponse(
            request_id=f"req-{uuid.uuid4().hex[:12]}",
            status=ResponseStatus.failed,
            errors=[{"code": "timeout", "message": REQUEST_TIMEOUT}],
            processing=ProcessingMeta(duration_ms=int((time.perf_counter() - started) * 1000)),
        )
