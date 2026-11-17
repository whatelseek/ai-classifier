"""System One routing question and answer parsing."""

import json

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.llm import joey_systemone
from app.llm.joey_systemone import (
    LLMUsageTracker,
    build_route_questions,
    classify_via_systemone,
    parse_choice_answer,
    reset_shared_client,
)


def test_route_question_is_choice_over_teams_and_unclassified():
    q = build_route_questions(Settings(_env_file=None))["route"]
    assert q["type"] == "choice"
    assert list(q["criteria"]) == [
        "database",
        "security",
        "network",
        "it_infrastructure",
        "unclassified",
    ]
    assert all(isinstance(v, str) and v for v in q["criteria"].values())


def test_parse_choice_picks_top_team():
    answer = {
        "type": "choice",
        "choice": "network",
        "probabilities": {
            "database": 0.01,
            "security": 0.04,
            "network": 0.80,
            "it_infrastructure": 0.12,
            "unclassified": 0.03,
        },
        "confidence": 0.75,
    }
    out = parse_choice_answer(answer)
    assert out.function == "network"
    assert out.confidence == pytest.approx(0.80)
    assert [a.function for a in out.alternatives] == ["it_infrastructure", "security"]


def test_parse_choice_unclassified_becomes_needs_review():
    answer = {
        "type": "choice",
        "choice": "unclassified",
        "probabilities": {
            "database": 0.01,
            "security": 0.01,
            "network": 0.01,
            "it_infrastructure": 0.02,
            "unclassified": 0.95,
        },
    }
    out = parse_choice_answer(answer)
    assert out.function == "needs_review"
    assert out.confidence == pytest.approx(0.95)
    assert all(a.function != "unclassified" for a in out.alternatives)


def test_parse_choice_without_probabilities_fails():
    with pytest.raises(ValueError):
        parse_choice_answer({"type": "choice", "choice": "security"})


def test_blank_routing_text_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, JOEY_CRITERIA_NETWORK="  ")


def test_systemone_needs_only_a_url():
    local = Settings(_env_file=None, JOEY_SYSTEMONE_URL="http://spark:8003/v1/systemone")
    assert local.joey_uses_systemone
    assert local.resolved_systemone_api_key is None
    assert local.joey_decision_model == "joey-1"
    assert not Settings(_env_file=None).joey_uses_systemone


async def _post_recording(monkeypatch, settings: Settings) -> httpx.Request:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        probs = {name: 0.02 for name in settings.joey_route_criteria}
        probs["security"] = 0.92
        return httpx.Response(
            200,
            json={
                "answers": {
                    "route": {"type": "choice", "choice": "security", "probabilities": probs}
                },
                "usage": {"input_tokens": 120, "output_tokens": 1},
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        joey_systemone.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    reset_shared_client()
    usage = LLMUsageTracker()
    out = await classify_via_systemone(settings, "много failed password в логах", usage)
    assert out.function == "security"
    assert usage.llm_calls == 1
    assert usage.token_usage["input"] == 120
    return seen[0]


async def test_local_endpoint_gets_no_authorization_header(monkeypatch):
    settings = Settings(
        _env_file=None,
        JOEY_SYSTEMONE_URL="http://spark:8003/v1/systemone",
        JOEY_DECISION_MODEL="joey-1",
    )
    request = await _post_recording(monkeypatch, settings)
    assert "authorization" not in request.headers
    assert str(request.url) == "http://spark:8003/v1/systemone"


async def test_api_key_is_sent_as_bearer(monkeypatch):
    settings = Settings(
        _env_file=None,
        JOEY_SYSTEMONE_URL="https://inference.baseten.co/v1/systemone",
        BASETEN_API_KEY="k-123",
    )
    request = await _post_recording(monkeypatch, settings)
    assert request.headers["authorization"] == "Bearer k-123"


async def test_question_and_criteria_come_from_env(monkeypatch):
    settings = Settings(
        _env_file=None,
        JOEY_SYSTEMONE_URL="http://spark:8003/v1/systemone",
        JOEY_ROUTE_INSTRUCTIONS="Which team?",
        JOEY_CRITERIA_DATABASE="databases",
        JOEY_CRITERIA_SECURITY="security events",
        JOEY_CRITERIA_NETWORK="vpn and firewalls",
        JOEY_CRITERIA_IT_INFRASTRUCTURE="servers and mail",
        JOEY_CRITERIA_UNCLASSIFIED="not an IT problem",
    )
    request = await _post_recording(monkeypatch, settings)
    body = json.loads(request.content)
    route = body["questions"]["route"]
    assert route["instructions"] == "Which team?"
    assert route["criteria"] == {
        "database": "databases",
        "security": "security events",
        "network": "vpn and firewalls",
        "it_infrastructure": "servers and mail",
        "unclassified": "not an IT problem",
    }


async def test_http_client_is_reused(monkeypatch):
    created: list[httpx.AsyncClient] = []
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "answers": {
                    "route": {
                        "type": "choice",
                        "choice": "network",
                        "probabilities": {"network": 0.9, "database": 0.1},
                    }
                },
                "usage": {"input_tokens": 4, "output_tokens": 1},
            },
        )

    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(handler), **kwargs)
        created.append(client)
        return client

    monkeypatch.setattr(joey_systemone.httpx, "AsyncClient", factory)
    reset_shared_client()
    settings = Settings(_env_file=None, JOEY_SYSTEMONE_URL="http://spark:8003/v1/systemone")
    usage = LLMUsageTracker()
    first = await classify_via_systemone(settings, "vpn", usage)
    second = await classify_via_systemone(settings, "vpn again", usage)
    assert first.function == "network"
    assert second.function == "network"
    assert len(created) == 1
    assert usage.llm_calls == 2
