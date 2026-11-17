"""HTTP route handlers for health, readiness, and ticket classification."""

import time
import uuid

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.dependencies import get_app_settings, get_request_semaphore
from app.core.config import Settings
from app.core.errors import REQUEST_TIMEOUT
from app.models.requests import ClassifyRequestPayload, UploadedAttachment
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


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for load balancers and orchestrators.

    Returns:
        Mapping with ``status`` set to ``ok``.
    """
    return {"status": "ok"}


@router.get("/ready")
async def ready(settings: Settings = Depends(get_app_settings)) -> dict[str, str | bool]:
    """Readiness probe including LLM configuration state.

    Args:
        settings: Application settings injected by FastAPI.

    Returns:
        Readiness payload with ``status`` and ``openai_configured`` flag.
    """
    return {
        "status": "ready",
        "openai_configured": settings.openai_configured,
        "joey_routing_mode": settings.joey_routing_mode,
        "joey_uses_systemone": settings.joey_uses_systemone,
        "joey_decision_model": settings.joey_decision_model,
    }


@router.get("/api/v1/functions", response_model=FunctionsListResponse)
async def list_functions() -> FunctionsListResponse:
    """List supported IT support function codes and descriptions.

    Returns:
        Catalog of routable support functions exposed by the classifier.
    """
    return build_functions_response()


@router.post("/api/v1/score", response_model=ClassifyResponse)
async def score_ticket(
    description: str | None = Form(default=None),
    issue_key: str | None = Form(default=None),
    client: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    settings: Settings = Depends(get_app_settings),
    semaphore=Depends(get_request_semaphore),
) -> ClassifyResponse:
    """Score-only routing: structured ``function`` + ``confidence``, no action text."""
    return await classify_ticket(
        description=description,
        issue_key=issue_key,
        client=client,
        files=files,
        settings=settings,
        semaphore=semaphore,
        scoring_only=True,
    )


@router.post("/api/v1/decide", response_model=DecideResponse)
async def decide_ticket(
    request: Request,
    settings: Settings = Depends(get_app_settings),
    semaphore=Depends(get_request_semaphore),
) -> DecideResponse:
    """Ticket description in, one decision out.

    Accepts JSON ``{"description": "..."}``, a form field ``description``,
    or a ``text/plain`` body.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        data = await request.json()
        description = data.get("description") if isinstance(data, dict) else None
    elif content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
        description = (await request.form()).get("description")
    else:
        description = (await request.body()).decode("utf-8", errors="replace")
    if not isinstance(description, str) or not description.strip():
        raise HTTPException(status_code=422, detail="description is required")

    response = await classify_ticket(
        description=description,
        issue_key=None,
        client=None,
        files=[],
        settings=settings,
        semaphore=semaphore,
        scoring_only=True,
    )
    confidence = response.classification.confidence if response.classification else 0.0
    return DecideResponse(decision=response.decision, confidence=confidence)


@router.post("/api/v1/classify", response_model=ClassifyResponse)
async def classify_ticket(
    description: str | None = Form(default=None),
    issue_key: str | None = Form(default=None),
    client: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    settings: Settings = Depends(get_app_settings),
    semaphore=Depends(get_request_semaphore),
    scoring_only: bool = False,
) -> ClassifyResponse:
    """Classify a ticket from multipart form text and optional file attachments.

    At least one of ``description`` or ``files`` must be provided. The request
    deadline starts before the concurrency semaphore, so queue wait counts
    toward ``REQUEST_TIMEOUT_SECONDS``.

    Args:
        description: Free-text ticket body.
        issue_key: Optional external ticket identifier.
        client: Optional client or tenant name.
        files: Uploaded attachments to parse and merge into context.
        settings: Application settings.
        semaphore: Limits concurrent in-flight classification requests.

    Returns:
        Structured classification result, per-attachment statuses, and metadata.
    """
    started = time.perf_counter()
    try:
        with anyio.fail_after(settings.request_timeout_seconds):
            async with semaphore:
                attachments: list[UploadedAttachment] = []
                for upload in files:
                    if upload.filename is None:
                        continue
                    data = await upload.read()
                    attachments.append(
                        UploadedAttachment(
                            filename=upload.filename,
                            content_type=upload.content_type,
                            data=data,
                            size=len(data),
                        )
                    )

                payload = ClassifyRequestPayload(
                    description=description,
                    issue_key=issue_key,
                    client=client,
                    attachments=attachments,
                )
                service = ClassificationService(settings)
                if scoring_only:
                    return await service.score(payload, started_at=started)
                return await service.classify(payload, started_at=started)
    except TimeoutError:
        return ClassifyResponse(
            request_id=f"req-{uuid.uuid4().hex[:12]}",
            status=ResponseStatus.failed,
            errors=[{"code": "timeout", "message": REQUEST_TIMEOUT}],
            processing=ProcessingMeta(
                duration_ms=int((time.perf_counter() - started) * 1000),
            ),
        )