"""Orchestrates validation, temp file handling, and LangGraph execution."""

import logging
import time
import uuid
from pathlib import Path

import anyio

from app.core.config import Settings, get_settings
from app.core.errors import INTERNAL_ERROR, REQUEST_TIMEOUT
from app.core.logging import request_id_var
from app.core.security import validate_extension, verify_file_signature
from app.graph.builder import get_graph
from app.graph.context import GraphContext
from app.llm.client import OpenAIClassificationClient
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
    """Runs the end-to-end classification pipeline for one ticket payload."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: OpenAIClassificationClient | None = None,
    ) -> None:
        """Initialize the service with settings and a compiled graph.

        Args:
            settings: Optional settings override; defaults to global settings.
            llm_client: Optional shared client. Tests inject a fake here.
        """
        self._settings = settings or get_settings()
        self._graph = get_graph()
        self._llm = llm_client or OpenAIClassificationClient(self._settings)

    async def classify(
        self,
        payload: ClassifyRequestPayload,
        started_at: float | None = None,
    ) -> ClassifyResponse:
        """Validate input, invoke LangGraph, and map state to a REST response.

        ``started_at`` is the moment the HTTP handler accepted the request, so
        time spent waiting for the concurrency semaphore counts toward
        ``REQUEST_TIMEOUT_SECONDS``.

        Args:
            payload: Normalized ticket description and attachments.
            started_at: Optional ``perf_counter`` timestamp from request start.

        Returns:
            ClassifyResponse with status, classification, and attachment details.
        """
        request_id = f"req-{uuid.uuid4().hex[:12]}"
        token = request_id_var.set(request_id)
        start = started_at if started_at is not None else time.perf_counter()
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
                "llm_calls": 0,
                "token_usage": {"input": 0, "output": 0, "total": 0},
                "processing": {
                    "model": self._settings.openai_text_model
                    if self._llm.is_available
                    else "heuristic",
                    "llm_calls": 0,
                },
            }

            remaining = self._settings.request_timeout_seconds - (time.perf_counter() - start)
            if remaining <= 0:
                raise TimeoutError
            context: GraphContext = {"llm_client": self._llm}
            with anyio.fail_after(remaining):
                final_state = await self._graph.ainvoke(
                    initial_state,
                    config={"max_concurrency": self._settings.max_concurrent_extraction},
                    context=context,
                )

            return self._build_response(request_id, final_state, start)
        except TimeoutError:
            logger.error("Request timed out", extra={"request_id": request_id})
            return ClassifyResponse(
                request_id=request_id,
                status=ResponseStatus.failed,
                errors=[{"code": "timeout", "message": REQUEST_TIMEOUT}],
                processing=ProcessingMeta(duration_ms=_duration_ms(start)),
            )
        except Exception:
            logger.exception("Classification pipeline failed")
            return ClassifyResponse(
                request_id=request_id,
                status=ResponseStatus.failed,
                errors=[{"code": "internal_error", "message": INTERNAL_ERROR}],
                processing=ProcessingMeta(duration_ms=_duration_ms(start)),
            )
        finally:
            request_id_var.reset(token)
            await anyio.to_thread.run_sync(self._cleanup, temp_paths)

    def _validate_uploads(self, payload: ClassifyRequestPayload) -> list[dict[str, str]]:
        """Enforce presence, count, size, extension, and signature rules.

        Args:
            payload: Incoming classification payload.

        Returns:
            List of error dicts; empty when validation succeeds.
        """
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
        """Write attachments to disk and build graph attachment metadata.

        Args:
            attachments: In-memory uploads.
            temp_paths: Output list mutated with paths for later cleanup.

        Returns:
            Attachment metadata dicts for LangGraph initial state.
        """
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
        """Remove temporary attachment files.

        Args:
            paths: Absolute paths created during persistence.
        """
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove temp file", extra={"path": str(path)})

    def _build_response(self, request_id: str, state: dict, start: float) -> ClassifyResponse:
        """Map final LangGraph state into the public API response model.

        Args:
            request_id: Correlation id for logging.
            state: Terminal graph state.
            start: ``perf_counter`` timestamp from request start.

        Returns:
            Validated ``ClassifyResponse``.
        """
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
    """Compute elapsed milliseconds since ``start``.

    Args:
        start: Value from ``time.perf_counter()``.

    Returns:
        Rounded duration in milliseconds.
    """
    return int((time.perf_counter() - start) * 1000)