"""Per-bucket tau thresholds + abstain semantics."""

import pytest

from brain.retrieval.tau import (
    DEFAULT_TAU,
    TAU_DEFAULTS,
    default_tau_for,
    should_abstain,
)


def test_default_tau_for_each_known_bucket() -> None:
    assert default_tau_for("semantic") == TAU_DEFAULTS["semantic"]
    assert default_tau_for("episodic") == TAU_DEFAULTS["episodic"]
    assert default_tau_for("procedural") == TAU_DEFAULTS["procedural"]
    assert default_tau_for("failure") == TAU_DEFAULTS["failure"]


def test_default_tau_for_none_returns_conservative() -> None:
    assert default_tau_for(None) == DEFAULT_TAU
    assert DEFAULT_TAU == 0.65


def test_default_tau_for_unknown_returns_conservative() -> None:
    assert default_tau_for("custom_bucket_we_dont_know") == DEFAULT_TAU


def test_should_abstain_semantics() -> None:
    assert should_abstain(top_score=None, tau=0.5) is True
    assert should_abstain(top_score=0.4, tau=0.5) is True
    assert should_abstain(top_score=0.5, tau=0.5) is False  # equal not below
    assert should_abstain(top_score=0.9, tau=0.5) is False


def test_recall_abstains_when_top_below_tau(monkeypatch, pg_url):
    """recall() returns [] when top fused/reranked score is below tau."""
    from brain.db import get_engine
    from brain.read import recall
    from brain.schemas import SourceInput
    from brain.write import write

    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="postgres is a relational database"))
    # FTS-only path: artificially set tau very high; ts_rank scores are < 1.
    hits = recall(engine, "postgres", k=5, tau=10.0)
    assert hits == []


def test_recall_returns_results_when_top_above_tau(pg_url):
    from brain.db import get_engine
    from brain.read import recall
    from brain.schemas import SourceInput
    from brain.write import write

    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="postgres is a relational database"))
    hits = recall(engine, "postgres", k=5, tau=0.0)
    assert len(hits) >= 1
