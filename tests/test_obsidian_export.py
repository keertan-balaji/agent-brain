"""Tests for DB → Obsidian markdown export."""

from pathlib import Path

from brain.db import get_engine
from brain.obsidian.export import export_brain_to_markdown
from brain.schemas import SourceInput
from brain.write import write


def test_export_writes_one_file_per_narrative_source(tmp_path: Path, pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(
        engine,
        SourceInput(
            kind="decision",
            content="# Pick redis for JWT store\n\nWhy: rotation cadence.",
        ),
    )
    write(
        engine,
        SourceInput(
            kind="gotcha", content="# FastAPI startup hook fires twice\n\nFix: ...",
        ),
    )
    out = tmp_path / "Agent-Brain"
    summary = export_brain_to_markdown(engine, out)
    assert summary.files_written >= 2
    # File names are slug-based; just verify directory contents exist.
    decisions = list((out / "agent-memory" / "decisions").glob("*.md"))
    gotchas = list((out / "agent-memory" / "gotchas").glob("*.md"))
    assert len(decisions) >= 1
    assert len(gotchas) >= 1


def test_exported_file_has_db_id_frontmatter(tmp_path: Path, pg_url: str) -> None:
    import frontmatter

    engine = get_engine(pg_url)
    res = write(
        engine, SourceInput(kind="decision", content="# Round-trip test\n\nBody.")
    )
    out = tmp_path / "Agent-Brain"
    export_brain_to_markdown(engine, out)
    files = list((out / "agent-memory" / "decisions").glob("*.md"))
    assert files
    # Cross-test pollution: other tests may have written decisions too. Find the
    # one matching the source_id we just wrote.
    matched = [
        frontmatter.load(f)
        for f in files
        if frontmatter.load(f).metadata.get("db_id") == res.source_id
    ]
    assert matched, f"no exported file matches db_id={res.source_id}"
    assert matched[0].metadata.get("db_id") == res.source_id


def test_tool_call_output_NOT_exported(tmp_path: Path, pg_url: str) -> None:  # noqa: N802
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="tool_call_output", content="huge stdout"))
    out = tmp_path / "Agent-Brain"
    export_brain_to_markdown(engine, out)
    # No subdir for tool_call_output should be created.
    assert not (out / "tool_calls").exists()
