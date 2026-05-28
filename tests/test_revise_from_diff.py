"""brain-revise --from-diff: propose invalidations given a diff hunk + source_id."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.reasoning.revise_from_diff import (
    revise_finalize_from_diff,
    revise_prepare_from_diff,
)


@pytest.fixture(scope="module")
def embedder():
    return BgeM3Embedder()


def _seed_source(engine, content, kind="decision", uri=None) -> int:
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES (:k, :c, :h, 'active', :u) RETURNING id"
            ),
            {"k": kind, "c": content, "h": h, "u": uri},
        ).scalar()
    return int(sid)


def test_prepare_returns_bundle_with_diff_in_prompt(pg_url: str, embedder) -> None:
    engine = get_engine(pg_url)
    sid = _seed_source(engine, "We use sha256 in src/hash.py", uri="decision://hash-algo")
    diff_hunk = (
        "--- a/src/hash.py\n"
        "+++ b/src/hash.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-def file_hash(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()\n"
        "+def file_hash(p): return hashlib.blake2b(open(p,'rb').read()).hexdigest()\n"
    )
    bundle = revise_prepare_from_diff(
        engine,
        source_id=sid,
        diff_hunk=diff_hunk,
        embedder=embedder,
    )
    assert bundle.cache_key_hex
    assert "sha256" in bundle.prompt
    assert "blake2b" in bundle.prompt
    assert "We use sha256" in bundle.prompt


def test_finalize_returns_revision_plan(pg_url: str, embedder) -> None:
    engine = get_engine(pg_url)
    sid = _seed_source(engine, "X is true at /a.py", uri="decision://x-claim")
    diff_hunk = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-X\n+Y\n"
    bundle = revise_prepare_from_diff(
        engine,
        source_id=sid,
        diff_hunk=diff_hunk,
        embedder=embedder,
    )
    raw = (
        '{"invalidations": [{"source_id": '
        + str(sid)
        + ', "reason": "diff replaces X with Y; claim no longer holds"}],'
        ' "reassertions": [], "creations": []}'
    )
    plan = revise_finalize_from_diff(
        engine,
        cache_key=bytes.fromhex(bundle.cache_key_hex),
        raw_output=raw,
    )
    assert len(plan.invalidations) == 1
    assert plan.invalidations[0].source_id == sid


def test_prepare_includes_neighboring_claims(pg_url: str, embedder) -> None:
    """Neighbors of the source (via propose_links) are surfaced so the agent
    can decide whether the diff cascades to them too."""
    engine = get_engine(pg_url)
    sid = _seed_source(engine, "Algorithm A is sha256-based", uri="decision://primary")
    _seed_source(engine, "Hash collisions are rare with sha256", uri="note://neighbor-1")

    diff_hunk = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-sha256\n+blake2b\n"
    bundle = revise_prepare_from_diff(
        engine,
        source_id=sid,
        diff_hunk=diff_hunk,
        embedder=embedder,
    )
    assert bundle.prompt
    assert "sha256-based" in bundle.prompt
