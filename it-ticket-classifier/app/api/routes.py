"""HTTP route handlers for health, readiness, and ticket classification."""

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import get_app_settings, get_request_semaphore
from app.core.config import Settings
from app.models.requests import ClassifyRequestPayload, UploadedAttachment
from app.models.responses import ClassifyResponse, FunctionsListResponse, build_functions_response
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
    }


@router.get("/api/v1/functions", response_model=FunctionsListResponse)
async def list_functions() -> FunctionsListResponse:
    """List supported IT support function codes and descriptions.

    Returns:
        Catalog of routable support functions exposed by the classifier.
    """
    return build_functions_response()


@router.post("/api/v1/classify", response_model=ClassifyResponse)
async def classify_ticket(
    description: str | None = Form(default=None),
    issue_key: str | None = Form(default=None),
    client: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    settings: Settings = Depends(get_app_settings),
    semaphore=Depends(get_request_semaphore),
) -> ClassifyResponse:
    """Classify a ticket from multipart form text and optional file attachments.

    At least one of ``description`` or ``files`` must be provided. Requests are
    bounded by a concurrency semaphore and the service-level timeout.

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
        return await service.classify(payload)