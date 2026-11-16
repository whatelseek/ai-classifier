"""Pydantic schemas for LLM structured classification output."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import SUPPORTED_FUNCTIONS

SupportFunctionLiteral = Literal["network", "linux", "security", "database"]


class LLMAlternative(BaseModel):
    """Secondary routing candidate returned by the model."""

    function: SupportFunctionLiteral
    score: float = Field(ge=0.0, le=1.0)


class LLMClassificationOutput(BaseModel):
    """Structured output schema validated after each LLM call.

    Attributes:
        function: Primary function or ``needs_review``.
        confidence: Model-reported confidence in ``[0, 1]``.
        reason: Short natural-language justification.
        alternatives: Other plausible functions with scores.
        evidence: Phrases supporting the decision.
    """

    function: Literal["network", "linux", "security", "database", "needs_review"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=2000)
    alternatives: list[LLMAlternative] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("function")
    @classmethod
    def validate_function(cls, v: str) -> str:
        """Reject function codes outside the configured enumeration.

        Args:
            v: Raw function string from the model.

        Returns:
            Validated function code.

        Raises:
            ValueError: When the function is not allowed.
        """
        if v == "needs_review":
            return v
        if v not in SUPPORTED_FUNCTIONS:
            raise ValueError(f"Invalid function: {v}")
        return v

    @field_validator("alternatives")
    @classmethod
    def validate_alternatives(cls, v: list[LLMAlternative]) -> list[LLMAlternative]:
        """Ensure alternative functions are members of the support enum.

        Args:
            v: Parsed alternative list.

        Returns:
            The same list when valid.

        Raises:
            ValueError: When any alternative uses an unknown function.
        """
        for alt in v:
            if alt.function not in SUPPORTED_FUNCTIONS:
                raise ValueError(f"Invalid alternative function: {alt.function}")
        return v


def _strict_classification_schema() -> dict:
    """Build an OpenAI strict-mode JSON schema for classification output.

    Returns:
        Schema with ``additionalProperties`` false and every property required.
    """
    from openai.lib._pydantic import to_strict_json_schema

    schema = to_strict_json_schema(LLMClassificationOutput)
    if not isinstance(schema, dict):
        raise TypeError("Strict classification schema must be a JSON object")
    return schema


CLASSIFICATION_JSON_SCHEMA = _strict_classification_schema()