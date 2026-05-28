"""brain.provenance — file hashing + provenance attachment + reverse lookup."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.provenance import (
    attach_provenance,
    file_hash,
    list_sources_for_files,
)


def test_file_hash_is_sha256_of_bytes(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("hello world\n")
    expected = hashlib.sha256(b"hello world\n").hexdigest()
    assert file_hash(f) == expected


def test_file_hash_returns_none_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.py"
    assert file_hash(missing) is None


def test_attach_provenance_writes_jsonb_to_source(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    f = tmp_path / "f.py"
    f.write_text("body\n")

    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'about f.py', :h, 'active') RETURNING id"
            ),
            {"h": sha256_bytes("about f.py")},
        ).scalar()

    attach_provenance(
        engine,
        source_id=int(sid),
        source_files=[{"path": str(f), "line_range": [1, 1]}],
        commit_at_capture="abc123",
        branch_at_capture="main",
    )

    with session_scope(engine) as s:
        meta = s.execute(
            text("SELECT provenance_meta FROM sources WHERE id = :i"), {"i": int(sid)}
        ).scalar()
    assert meta is not None
    assert meta["commit_at_capture"] == "abc123"
    assert meta["branch_at_capture"] == "main"
    assert len(meta["source_files"]) == 1
    sf = meta["source_files"][0]
    assert sf["path"] == str(f)
    assert sf["line_range"] == [1, 1]
    # sha256_at_capture auto-computed from the file contents.
    import hashlib as _h
    assert sf["sha256_at_capture"] == _h.sha256(b"body\n").hexdigest()


def test_attach_provenance_skips_missing_files(pg_url: str, tmp_path: Path) -> None:
    """If a referenced file doesn't exist at capture-time, sha256 is null but the
    entry still records its declared path (lets staleness scan flag it later)."""
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'no file', :h, 'active') RETURNING id"
            ),
            {"h": sha256_bytes("no file")},
        ).scalar()

    missing = tmp_path / "nope.py"
    attach_provenance(
        engine,
        source_id=int(sid),
        source_files=[{"path": str(missing)}],
    )

    with session_scope(engine) as s:
        meta = s.execute(
            text("SELECT provenance_meta FROM sources WHERE id = :i"), {"i": int(sid)}
        ).scalar()
    assert meta["source_files"][0]["sha256_at_capture"] is None


def test_list_sources_for_files_finds_match(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    f = tmp_path / "g.py"
    f.write_text("g body\n")

    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('gotcha', 'about g.py', :h, 'active') RETURNING id"
            ),
            {"h": sha256_bytes("about g.py")},
        ).scalar()
    attach_provenance(engine, source_id=int(sid), source_files=[{"path": str(f)}])

    matches = list_sources_for_files(engine, paths=[str(f)])
    assert int(sid) in {row.source_id for row in matches}


def test_list_sources_for_files_empty_paths(pg_url: str) -> None:
    engine = get_engine(pg_url)
    assert list_sources_for_files(engine, paths=[]) == []


def test_list_sources_for_files_ignores_invalidated(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    f = tmp_path / "h.py"
    f.write_text("h\n")
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, t_valid_to) "
                "VALUES ('note', 'invalidated', :h, 'active', NOW()) RETURNING id"
            ),
            {"h": sha256_bytes("invalidated")},
        ).scalar()
    attach_provenance(engine, source_id=int(sid), source_files=[{"path": str(f)}])
    matches = list_sources_for_files(engine, paths=[str(f)])
    assert int(sid) not in {row.source_id for row in matches}
