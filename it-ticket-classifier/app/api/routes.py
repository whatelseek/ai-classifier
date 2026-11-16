from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import get_app_settings, get_request_semaphore
from app.core.config import Settings
from app.models.requests import ClassifyRequestPayload, UploadedAttachment
from app.models.responses import ClassifyResponse, FunctionsListResponse, build_functions_response
from app.services.classifier import ClassificationService

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(settings: Settings = Depends(get_app_settings)) -> dict[str, str | bool]:
    return {
        "status": "ready",
        "openai_configured": settings.openai_configured,
    }


@router.get("/api/v1/functions", response_model=FunctionsListResponse)
async def list_functions() -> FunctionsListResponse:
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