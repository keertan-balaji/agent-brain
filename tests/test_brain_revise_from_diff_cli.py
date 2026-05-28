"""brain revise prepare-from-diff / finalize-from-diff CLI."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope


def _run(args, pg_url, stdin=None):
    return subprocess.run(
        ["brain", *args],
        input=stdin,
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": pg_url},
    )


def test_prepare_from_diff_emits_prompt_and_cache_key(pg_url: str) -> None:
    engine = get_engine(pg_url)
    content = "X is true at /a.py"
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', :c, :h, 'active') RETURNING id"
            ),
            {"c": content, "h": h},
        ).scalar()

    diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-X\n+Y\n"
    res = _run(
        ["revise", "prepare-from-diff",
         "--source-id", str(int(sid)),
         "--diff", diff],
        pg_url,
    )
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)
    assert payload["cache_key"]
    assert "X" in payload["prompt"]
    assert "+Y" in payload["prompt"]


def test_finalize_from_diff_validates_and_returns_plan(pg_url: str) -> None:
    """Full round-trip: prepare emits cache_key + prompt; finalize accepts the
    agent-generated JSON and returns a DiffRevisionPlan."""
    engine = get_engine(pg_url)
    content = "Algo A is correct"
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', :c, :h, 'active') RETURNING id"
            ),
            {"c": content, "h": h},
        ).scalar()

    diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-Algo A\n+Algo B\n"
    prep_res = _run(
        ["revise", "prepare-from-diff",
         "--source-id", str(int(sid)),
         "--diff", diff],
        pg_url,
    )
    assert prep_res.returncode == 0, prep_res.stderr
    cache_key = json.loads(prep_res.stdout)["cache_key"]

    raw_output = (
        '{"invalidations": [{"source_id": '
        + str(int(sid))
        + ', "reason": "Algo A replaced by Algo B in diff"}],'
        ' "reassertions": [], "creations": []}'
    )
    fin_res = _run(
        ["revise", "finalize-from-diff",
         "--cache-key", cache_key,
         "--output", raw_output],
        pg_url,
    )
    assert fin_res.returncode == 0, fin_res.stderr
    plan = json.loads(fin_res.stdout)
    assert plan["invalidations"][0]["source_id"] == int(sid)
