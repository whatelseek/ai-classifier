"""Public decision labels."""

import pytest

from app.core.routing import to_decision
from app.llm.schemas import LLMClassificationOutput


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("database", "database"),
        ("security", "security"),
        ("network", "network"),
        ("it_infrastructure", "it_infrastructure"),
        ("linux", "it_infrastructure"),
        ("needs_review", "unclassified"),
        ("unclassified", "unclassified"),
        (None, "unclassified"),
        ("bogus", "unclassified"),
    ],
)
def test_to_decision(raw, expected):
    assert to_decision(raw) == expected


def test_model_output_accepts_unclassified_and_linux():
    assert LLMClassificationOutput(function="unclassified", confidence=0.2, reason="x").function == "needs_review"
    assert LLMClassificationOutput(function="linux", confidence=0.8, reason="x").function == "it_infrastructure"