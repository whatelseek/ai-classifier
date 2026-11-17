"""Tests for partial Joey/vLLM JSON recovery."""

from app.llm.client import _salvage_classification_json


def test_salvage_truncated_database():
    out = _salvage_classification_json('{"function":"database",')
    assert out is not None
    assert out.function == "database"
    assert out.confidence >= 0.5