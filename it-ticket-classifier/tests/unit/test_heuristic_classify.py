"""Unit tests for the offline heuristic classification fallback."""

from app.graph.nodes.classify import _heuristic_classify


def test_heuristic_network():
    out = _heuristic_classify("Configure IPsec VPN on MikroTik", "")
    assert out["function"] == "network"


def test_heuristic_database():
    out = _heuristic_classify("PostgreSQL replication is broken", "")
    assert out["function"] == "database"


def test_heuristic_ambiguous():
    out = _heuristic_classify("General question about IT", "")
    assert out["function"] == "needs_review"


def test_heuristic_database_russian():
    out = _heuristic_classify("Плановое обслуживание PostgreSQL и проверка резервных копий", "")
    assert out["function"] == "database"