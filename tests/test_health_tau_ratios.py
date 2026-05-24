"""brain-health tau-rolling-ratio per bucket."""

from __future__ import annotations

import json

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.helpers.health import audit


def _plant_log_row(
    engine, *, bucket: str, selected: list[int] | None, candidates: list[dict]
) -> None:
    with session_scope(engine) as s:
        s.execute(
            text(
                """
                INSERT INTO retrieval_log(query, filters, candidates, selected, abstained, top1_score)
                VALUES (:q, CAST(:f AS jsonb), CAST(:c AS jsonb), :sel, FALSE, 0.5)
                """
            ),
            {
                "q": "any",
                "f": json.dumps({"buckets": [bucket]}),
                "c": json.dumps(candidates),
                "sel": selected,
            },
        )


def test_tau_ratio_is_none_when_no_selected_data(pg_url):
    engine = get_engine(pg_url)
    _plant_log_row(
        engine, bucket="semantic", selected=None, candidates=[{"id": 1, "score": 0.9}]
    )
    report = audit(engine)
    assert report.tau_rolling_ratios.get("semantic") is None


def test_tau_ratio_averages_across_rows(pg_url):
    engine = get_engine(pg_url)
    # row 1: selected 2/4 = 0.5
    _plant_log_row(
        engine,
        bucket="semantic",
        selected=[1, 2],
        candidates=[{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}],
    )
    # row 2: selected 1/2 = 0.5
    _plant_log_row(
        engine,
        bucket="semantic",
        selected=[1],
        candidates=[{"id": 1}, {"id": 2}],
    )
    report = audit(engine)
    assert abs(report.tau_rolling_ratios["semantic"] - 0.5) < 1e-6


def test_tau_ratio_per_bucket_independent(pg_url):
    engine = get_engine(pg_url)
    _plant_log_row(
        engine,
        bucket="episodic",
        selected=[1, 2, 3],
        candidates=[{"id": i} for i in range(10)],
    )
    _plant_log_row(
        engine,
        bucket="procedural",
        selected=[1],
        candidates=[{"id": 1}],
    )
    report = audit(engine)
    assert abs(report.tau_rolling_ratios["episodic"] - 0.3) < 1e-6
    assert abs(report.tau_rolling_ratios["procedural"] - 1.0) < 1e-6
    # untouched buckets remain None
    assert report.tau_rolling_ratios.get("semantic") is None
    assert report.tau_rolling_ratios.get("failure") is None


def test_tau_ratio_includes_all_four_buckets_in_report(pg_url):
    engine = get_engine(pg_url)
    report = audit(engine)
    assert set(report.tau_rolling_ratios.keys()) == {
        "semantic",
        "episodic",
        "procedural",
        "failure",
    }
