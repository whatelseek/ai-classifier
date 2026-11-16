from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import SUPPORTED_FUNCTIONS

SupportFunctionLiteral = Literal["network", "linux", "security", "database"]


class LLMAlternative(BaseModel):
    function: SupportFunctionLiteral
    score: float = Field(ge=0.0, le=1.0)


class LLMClassificationOutput(BaseModel):
    """Structured output schema for OpenAI classification."""

    function: SupportFunctionLiteral | Literal["needs_review"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=2000)
    alternatives: list[LLMAlternative] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("function")
    @classmethod
    def validate_function(cls, v: str) -> str:
        if v == "needs_review":
            return v
        if v not in SUPPORTED_FUNCTIONS:
            raise ValueError(f"Invalid function: {v}")
        return v

    @field_validator("alternatives")
    @classmethod
    def validate_alternatives(cls, v: list[LLMAlternative]) -> list[LLMAlternative]:
        for alt in v:
            if alt.function not in SUPPORTED_FUNCTIONS:
                raise ValueError(f"Invalid alternative function: {alt.function}")
        return v


CLASSIFICATION_JSON_SCHEMA = LLMClassificationOutput.model_json_schema()