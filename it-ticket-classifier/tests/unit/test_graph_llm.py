"""Graph tests with a fake Responses client. No network calls."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.graph.builder import build_classification_graph
from app.llm.client import LLMUsageTracker
from app.llm.schemas import LLMClassificationOutput


class FakeLLM:
    """Records prompts and returns scripted classification results."""

    is_available = True

    def __init__(self, results: list[LLMClassificationOutput | Exception]) -> None:
        self._results = list(results)
        self.feedback: list[str | None] = []
        self.image_prompts: list[str] = []

    async def classify(
        self,
        description: str,
        merged_context: str,
        client: str | None,
        issue_key: str | None,
        usage: LLMUsageTracker,
        retry_feedback: str | None = None,
    ) -> LLMClassificationOutput:
        del description, merged_context, client, issue_key
        self.feedback.append(retry_feedback)
        usage.record(SimpleNamespace(input_tokens=10, output_tokens=4, total_tokens=14))
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def analyze_image(
        self,
        image_bytes: bytes,
        media_type: str,
        prompt: str,
        usage: LLMUsageTracker,
    ) -> str:
        del image_bytes, media_type
        self.image_prompts.append(prompt)
        usage.record(SimpleNamespace(input_tokens=3, output_tokens=2, total_tokens=5))
        return "password=SuperSecret123 hostname db-1"


def _state(**overrides: object) -> dict:
    state = {
        "request_id": "req-test",
        "issue_key": None,
        "client": None,
        "description": "IPsec VPN tunnel down on Check Point",
        "attachments": [],
        "attachment_statuses": [],
        "extracted_content": [],
        "retry_count": 0,
        "status": "pending",
        "errors": [],
        "llm_calls": 0,
        "token_usage": {"input": 0, "output": 0, "total": 0},
    }
    state.update(overrides)
    return state


def _ok(confidence: float = 0.91) -> LLMClassificationOutput:
    return LLMClassificationOutput(
        function="network",
        confidence=confidence,
        reason="VPN connectivity",
        alternatives=[],
        evidence=["IPsec"],
    )


@pytest.mark.asyncio
async def test_mocked_llm_classifies_and_counts_tokens():
    fake = FakeLLM([_ok()])
    graph = build_classification_graph()
    result = await graph.ainvoke(
        _state(),
        context={"llm_client": fake},
        config={"max_concurrency": 2},
    )
    assert result["status"] == "classified"
    assert result["classification"]["function"] == "network"
    assert result["llm_calls"] == 1
    assert result["token_usage"]["input"] == 10
    assert fake.feedback == [None]


@pytest.mark.asyncio
async def test_invalid_output_retries_with_different_prompt():
    fake = FakeLLM([ValueError("not json"), _ok()])
    graph = build_classification_graph()
    result = await graph.ainvoke(_state(), context={"llm_client": fake})
    assert result["status"] == "classified"
    assert result["classification"]["function"] == "network"
    assert fake.feedback[0] in (None, "")
    assert fake.feedback[1]
    assert "could not be parsed" in fake.feedback[1]
    assert "not json" not in fake.feedback[1]
    assert result.get("errors") in ([], None)


@pytest.mark.asyncio
async def test_low_confidence_retry_mentions_previous_score():
    fake = FakeLLM([_ok(0.5), _ok(0.93)])
    graph = build_classification_graph()
    result = await graph.ainvoke(_state(), context={"llm_client": fake})
    assert result["status"] == "classified"
    assert result["confidence"] == 0.93
    assert result["retry_count"] == 1
    assert "0.50" in (fake.feedback[1] or "")
    assert result["llm_calls"] == 2
    assert result["token_usage"]["total"] == 28


@pytest.mark.asyncio
async def test_image_tokens_are_kept_alongside_classification(tmp_path: Path):
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    fake = FakeLLM([_ok()])
    graph = build_classification_graph()
    result = await graph.ainvoke(
        _state(
            attachments=[
                {
                    "filename": "shot.png",
                    "content_type": "image/png",
                    "size": image.stat().st_size,
                    "category": "image",
                    "path": str(image),
                }
            ]
        ),
        context={"llm_client": fake},
        config={"max_concurrency": 2},
    )
    assert result["status"] == "classified"
    assert result["llm_calls"] == 2
    assert result["token_usage"]["input"] == 13
    assert result["token_usage"]["total"] == 19
    statuses = result["attachment_statuses"]
    assert statuses[0]["status"] == "processed"
    merged = result["merged_context"]
    assert "SuperSecret123" not in merged
    assert "[REDACTED_SECRET]" in merged
    assert any("password" in prompt.lower() or "secret" in prompt.lower() for prompt in fake.image_prompts)
