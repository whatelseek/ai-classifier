"""Unit tests for LangGraph conditional routing helpers."""

from app.graph.edges import route_after_confidence, route_after_validate


def test_route_after_validate_failure():
    assert (
        route_after_validate({"status": "failed"})
        == "return_validation_error"
    )


def test_route_after_validate_ok():
    assert route_after_validate({"status": "validated"}) == "detect_attachments"


def test_route_retry_bounded():
    state = {
        "status": "classified",
        "confidence": 0.3,
        "retry_count": 0,
        "classification": {"function": "network"},
    }
    assert route_after_confidence(state) == "retry_classification"

    state["retry_count"] = 2
    assert route_after_confidence(state) == "format_response"