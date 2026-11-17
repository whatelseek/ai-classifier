"""System One score parsing (Baseten Playground parity)."""

from app.llm.joey_systemone import build_playground_score_questions, parse_score_answer


def test_playground_question_shape():
    q = build_playground_score_questions()["route"]
    assert q["type"] == "score"
    assert q["instructions"] == "К какой категории относится обращение?"
    assert q["criteria"] == ["database", "security", "network", "it_infrastructure"]


def test_parse_score_antivirus_like_playground():
    answer = {
        "type": "score",
        "score": 0.33,
        "confidence": 0.97,
        "probabilities": {"0": 0.005, "1": 0.985, "2": 0.005, "3": 0.005},
    }
    out = parse_score_answer(answer)
    assert out.function == "security"
    assert out.confidence >= 0.9