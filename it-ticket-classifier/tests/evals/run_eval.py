"""Offline evaluation using heuristic classifier (no OpenAI required)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app.graph.nodes.classify import _heuristic_classify

CASES_PATH = Path(__file__).with_name("labeled_cases.json")
LABELS = ("network", "linux", "security", "database", "needs_review")


def main() -> None:
    cases = json.loads(CASES_PATH.read_text())
    y_true: list[str] = []
    y_pred: list[str] = []

    for case in cases:
        out = _heuristic_classify(case["description"], "")
        pred = out["function"]
        y_true.append(case["expected"])
        y_pred.append(pred)

    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for t, p in zip(y_true, y_pred, strict=True):
        matrix[t][p] += 1

    # Macro-F1 over non-abstain classes for routing accuracy
    f1s = []
    for label in ("network", "linux", "security", "database"):
        tp = matrix[label][label]
        fp = sum(matrix[t][label] for t in LABELS if t != label)
        fn = sum(matrix[label][p] for p in LABELS if p != label)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        f1s.append(f1)

    macro_f1 = sum(f1s) / len(f1s)
    abstain = sum(1 for t, p in zip(y_true, y_pred, strict=True) if p == "needs_review")
    false_route = sum(
        1
        for t, p in zip(y_true, y_pred, strict=True)
        if t != "needs_review" and p != "needs_review" and t != p
    )

    print(json.dumps({
        "cases": len(cases),
        "macro_f1_heuristic": round(macro_f1, 3),
        "abstention_rate": round(abstain / len(cases), 3),
        "false_routing_rate": round(false_route / len(cases), 3),
        "confusion_matrix": {k: dict(v) for k, v in matrix.items()},
        "note": "Live OpenAI eval requires pytest -m live_openai (not enabled by default)",
    }, indent=2))


if __name__ == "__main__":
    main()