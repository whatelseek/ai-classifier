"""Unit tests for LangGraph conditional routing helpers."""

from app.graph.edges import fan_out_processing, route_after_confidence, route_after_validate


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
        "classification": {"function": "it_infrastructure"},
    }
    assert route_after_confidence(state) == "retry_classification"

    state["retry_count"] = 2
    assert route_after_confidence(state) == "format_response"


def test_route_parse_failure_retries_until_budget():
    state = {"status": "retry", "retry_count": 0, "confidence": 0.0, "classification": {}}
    assert route_after_confidence(state) == "retry_classification"
    state["retry_count"] = 2
    assert route_after_confidence(state) == "format_response"


def test_fan_out_one_send_per_file():
    state = {
        "request_id": "req-1",
        "description": "see attachments",
        "attachments": [
            {"filename": "a.log"},
            {"filename": "b.log"},
            {"filename": "shot.png"},
            {"filename": "net.vsdx"},
        ],
        "retry_count": 0,
        "status": "validated",
    }
    sends = fan_out_processing(state)
    targets = [item.node for item in sends]
    assert targets.count("process_text") == 1
    assert targets.count("process_documents") == 2
    assert targets.count("process_images") == 1
    assert targets.count("process_diagrams") == 1
    workers = [item for item in sends if item.node != "process_text"]
    assert all(len(item.arg["attachments"]) == 1 for item in workers)