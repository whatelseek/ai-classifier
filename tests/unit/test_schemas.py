"""Unit tests for LLM structured output schema validation."""

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from app.llm.schemas import CLASSIFICATION_JSON_SCHEMA, LLMClassificationOutput


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


def _assert_strict_object(schema: dict) -> None:
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False
        properties = schema.get("properties") or {}
        assert set(schema.get("required") or []) == set(properties)
    for nested in schema.get("$defs", {}).values():
        if isinstance(nested, dict):
            _assert_strict_object(nested)


def test_classification_schema_is_strict():
    assert CLASSIFICATION_JSON_SCHEMA == to_strict_json_schema(LLMClassificationOutput)
    _assert_strict_object(CLASSIFICATION_JSON_SCHEMA)
    assert "needs_review" in CLASSIFICATION_JSON_SCHEMA["properties"]["function"]["enum"]


def test_classification_schema_rejects_invalid_function():
    with pytest.raises(ValidationError):
        LLMClassificationOutput.model_validate(
            {
                "function": "helpdesk",
                "confidence": 0.9,
                "reason": "x",
            }
        )