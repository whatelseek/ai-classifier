"""System One score parsing (Baseten Playground parity)."""

from app.llm.joey_systemone import build_playground_score_questions, parse_score_answer


def test_playground_question_shape():
    q = build_playground_score_questions()["route"]
    assert q["type"] == "score"
    assert q["instructions"] == "К какой категории относится обращение?"
    assert q["criteria"] == ["network", "linux", "security", "database"]


def test_parse_score_antivirus_like_playground():
    answer = {
      "type": "score",
      "score": 0.02,
      "confidence": 0.97,
      "probabilities": {"0": 0.005, "1": 0.005, "2": 0.988, "3": 0.002},
      "legend": {
          "0": "network",
          "1": "linux",
          "2": "security",
          "3": "database",
      },
    }
    out = parse_score_answer(answer)
    assert out.function == "security"
    assert out.confidence >= 0.9