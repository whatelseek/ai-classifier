import logging
import time
import uuid
from pathlib import Path

import anyio

from app.core.config import Settings, get_settings
from app.core.logging import request_id_var
from app.core.security import validate_extension, verify_file_signature
from app.graph.builder import get_graph
from app.models.requests import ClassifyRequestPayload, UploadedAttachment
from app.models.responses import (
    AttachmentStatusItem,
    ClassificationResult,
    ClassifyResponse,
    ProcessingMeta,
    ResponseStatus,
)

logger = logging.getLogger(__name__)


class ClassificationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._graph = get_graph()

    async def classify(self, payload: ClassifyRequestPayload) -> ClassifyResponse:
        request_id = f"req-{uuid.uuid4().hex[:12]}"
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        temp_paths: list[Path] = []

        try:
            validation_errors = self._validate_uploads(payload)
            if validation_errors:
                return ClassifyResponse(
                    request_id=request_id,
                    status=ResponseStatus.failed,
                    errors=validation_errors,
                    processing=ProcessingMeta(duration_ms=_duration_ms(start)),
                )

            attachments_meta = await anyio.to_thread.run_sync(
                self._persist_attachments, payload.attachments, temp_paths
            )

            initial_state = {
                "request_id": request_id,
                "issue_key": payload.issue_key,
                "client": payload.client,
                "description": payload.description or "",
                "attachments": attachments_meta,
                "attachment_statuses": [],
                "extracted_content": [],
                "retry_count": 0,
                "status": "pending",
                "errors": [],
                "processing": {
                    "model": self._settings.openai_text_model
                    if self._settings.openai_configured
                    else "heuristic",
                    "llm_calls": 0,
                },
            }

            with anyio.fail_after(self._settings.request_timeout_seconds):
                final_state = await self._graph.ainvoke(initial_state)

            return self._build_response(request_id, final_state, start)
        except TimeoutError:
            logger.error("Request timed out", extra={"request_id": request_id})
            return ClassifyResponse(
                request_id=request_id,
                status=ResponseStatus.failed,
                errors=[{"code": "timeout", "message": "Request processing timed out"}],
                processing=ProcessingMeta(duration_ms=_duration_ms(start)),
            )
        except Exception as exc:
            logger.exception("Classification pipeline failed")
            return ClassifyResponse(
                request_id=request_id,
                status=ResponseStatus.failed,
                errors=[{"code": "internal_error", "message": str(exc)}],
                processing=ProcessingMeta(duration_ms=_duration_ms(start)),
            )
        finally:
            request_id_var.reset(token)
            await anyio.to_thread.run_sync(self._cleanup, temp_paths)

    def _validate_uploads(self, payload: ClassifyRequestPayload) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        if not (payload.description or "").strip() and not payload.attachments:
            errors.append(
                {
                    "code": "validation_error",
                    "message": "At least one of description or files must be provided",
                }
            )
            return errors

        if len(payload.attachments) > self._settings.max_attachments:
            errors.append(
                {
                    "code": "validation_error",
                    "message": f"Maximum {self._settings.max_attachments} attachments allowed",
                }
            )

        total = sum(a.size for a in payload.attachments)
        if total > self._settings.max_total_upload_bytes:
            errors.append(
                {
                    "code": "validation_error",
                    "message": "Total upload size exceeds limit",
                }
            )

        for att in payload.attachments:
            if att.size > self._settings.max_file_size_bytes:
                errors.append(
                    {
                        "code": "validation_error",
                        "message": f"File {att.filename} exceeds size limit",
                    }
                )
            ext_err = validate_extension(att.filename)
            if ext_err:
                errors.append({"code": "validation_error", "message": ext_err})
            elif not verify_file_signature(att.data, att.filename.rsplit(".", 1)[-1].lower()):
                errors.append(
                    {
                        "code": "validation_error",
                        "message": f"File signature mismatch for {att.filename}",
                    }
                )
        return errors

    def _persist_attachments(
        self, attachments: list[UploadedAttachment], temp_paths: list[Path]
    ) -> list[dict]:
        from app.parsers.registry import category_for_filename

        self._settings.temp_dir.mkdir(parents=True, exist_ok=True)
        metas: list[dict] = []
        for att in attachments:
            path = self._settings.temp_dir / f"{uuid.uuid4().hex}_{Path(att.filename).name}"
            path.write_bytes(att.data)
            temp_paths.append(path)
            metas.append(
                {
                    "filename": att.filename,
                    "content_type": att.content_type,
                    "size": att.size,
                    "category": category_for_filename(att.filename),
                    "path": str(path),
                }
            )
        return metas

    def _cleanup(self, paths: list[Path]) -> None:
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove temp file", extra={"path": str(path)})

    def _build_response(self, request_id: str, state: dict, start: float) -> ClassifyResponse:
        status_str = state.get("status", "failed")
        try:
            status = ResponseStatus(status_str)
        except ValueError:
            status = ResponseStatus.failed

        classification = None
        raw_cls = state.get("classification")
        if raw_cls and isinstance(raw_cls, dict):
            classification = ClassificationResult.model_validate(raw_cls)

        attachments = [
            AttachmentStatusItem(
                filename=a["filename"],
                status=a["status"],
                parser=a.get("parser"),
                error=a.get("error"),
            )
            for a in state.get("attachment_statuses") or []
        ]

        proc = state.get("processing") or {}
        proc["duration_ms"] = _duration_ms(start)
        proc["llm_calls"] = state.get("llm_calls", proc.get("llm_calls", 0))
        if state.get("token_usage"):
            proc["token_usage"] = state.get("token_usage")

        return ClassifyResponse(
            request_id=request_id,
            status=status,
            classification=classification,
            attachments=attachments,
            processing=ProcessingMeta.model_validate(proc),
            errors=state.get("errors") or [],
        )


def _duration_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)