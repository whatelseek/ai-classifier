"""Pydantic response models for the public REST API."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import SUPPORTED_FUNCTIONS

SupportFunction = Literal["network", "linux", "security", "database"]


class ResponseStatus(str, Enum):
    """Top-level outcome for a classification request."""

    classified = "classified"
    needs_review = "needs_review"
    failed = "failed"


class AlternativeFunction(BaseModel):
    """Runner-up support function with a relative score."""

    function: SupportFunction
    score: float = Field(ge=0.0, le=1.0)


class ClassificationResult(BaseModel):
    """Model routing decision and explanatory fields."""

    function: SupportFunction | Literal["needs_review"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    alternatives: list[AlternativeFunction] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class AttachmentStatusItem(BaseModel):
    """Per-file extraction outcome reported to the client."""

    filename: str
    status: Literal["processed", "failed", "skipped"]
    parser: str | None = None
    error: str | None = None


class ProcessingMeta(BaseModel):
    """Timing, model id, and token accounting for the request."""

    model: str | None = None
    llm_calls: int = 0
    duration_ms: int = 0
    token_usage: dict[str, int] | None = None


class ClassifyResponse(BaseModel):
    """Complete REST response for ``POST /api/v1/classify``."""

    request_id: str
    status: ResponseStatus
    classification: ClassificationResult | None = None
    attachments: list[AttachmentStatusItem] = Field(default_factory=list)
    processing: ProcessingMeta = Field(default_factory=ProcessingMeta)
    errors: list[dict[str, str]] = Field(default_factory=list)


class FunctionInfo(BaseModel):
    """One row in the support-function catalog."""

    code: str
    name: str
    scope: str


class FunctionsListResponse(BaseModel):
    """Response wrapper for ``GET /api/v1/functions``."""

    functions: list[FunctionInfo]


FUNCTION_SCOPES: dict[str, str] = {
    "network": "VPN, routing, DNS, BGP, VLAN, firewall connectivity, MikroTik, Check Point",
    "linux": "Debian, Ubuntu, RHEL, SSH, systemd, Linux services, OS configuration",
    "security": "SIEM, EDR, DLP, PAM, security incidents, security monitoring",
    "database": "PostgreSQL, Microsoft SQL Server, MySQL, replication, SQL performance",
}


def build_functions_response() -> FunctionsListResponse:
    """Build the static list of routable IT support functions.

    Returns:
        FunctionsListResponse containing all configured function codes.
    """
    from app.core.config import FUNCTION_DISPLAY_NAMES

    return FunctionsListResponse(
        functions=[
            FunctionInfo(
                code=code,
                name=FUNCTION_DISPLAY_NAMES[code],
                scope=FUNCTION_SCOPES[code],
            )
            for code in SUPPORTED_FUNCTIONS
        ]
    )