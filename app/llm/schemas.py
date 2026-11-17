"""Pydantic schema for one routing decision."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import SUPPORTED_FUNCTIONS
from app.core.routing import normalize_routing_function

SupportFunctionLiteral = Literal["database", "security", "network", "it_infrastructure"]


class LLMAlternative(BaseModel):
    """Secondary routing candidate returned by the model."""

    function: SupportFunctionLiteral
    score: float = Field(ge=0.0, le=1.0)


class LLMClassificationOutput(BaseModel):
    """One decision. ``unclassified`` from Joey is stored as ``needs_review``."""

    function: Literal["database", "security", "network", "it_infrastructure", "needs_review"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=240)
    alternatives: list[LLMAlternative] = Field(default_factory=list, max_length=2)
    evidence: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("function", mode="before")
    @classmethod
    def validate_function(cls, value: str) -> str:
        """Map legacy labels and reject anything outside the enumeration."""
        raw = str(value).strip().lower()
        normalized = normalize_routing_function(raw)
        if normalized == "needs_review" and raw not in ("needs_review", "unclassified"):
            raise ValueError(f"Invalid function: {value}")
        return normalized

    @field_validator("alternatives")
    @classmethod
    def validate_alternatives(cls, value: list[LLMAlternative]) -> list[LLMAlternative]:
        """Keep only the four support teams as alternatives."""
        for alt in value:
            if alt.function not in SUPPORTED_FUNCTIONS:
                raise ValueError(f"Invalid alternative function: {alt.function}")
        return value
