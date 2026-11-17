"""Validation of one routing decision."""

import pytest
from pydantic import ValidationError

from app.llm.schemas import LLMClassificationOutput


def test_classification_schema_valid():
    obj = LLMClassificationOutput.model_validate(
        {
            "function": "it_infrastructure",
            "confidence": 0.9,
            "reason": "VPN issue",
            "alternatives": [{"function": "security", "score": 0.2}],
            "evidence": ["IPsec"],
        }
    )
    assert obj.function == "it_infrastructure"


def test_classification_schema_rejects_invalid_function():
    with pytest.raises(ValidationError):
        LLMClassificationOutput.model_validate(
            {"function": "helpdesk", "confidence": 0.9, "reason": "x"}
        )
