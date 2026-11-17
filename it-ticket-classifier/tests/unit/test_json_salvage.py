"""Tests for partial Joey/vLLM JSON recovery."""

from app.llm.client import _normalize_vllm_structured_json, _parse_classification_json, _salvage_classification_json


def test_salvage_truncated_database():
    out = _salvage_classification_json('{"function":"database",')
    assert out is not None
    assert out.function == "database"
    assert out.confidence >= 0.5


def test_normalize_vllm_tab_padding():
    raw = '{"function":"network","confidence":\t\t\t\t\t\t'
    normalized = _normalize_vllm_structured_json(raw)
    out = _parse_classification_json(normalized)
    assert out.function == "network"
    assert out.confidence >= 0.5