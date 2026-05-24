"""CLI smoke tests: subcommands registered + health renders against a real DB."""

from __future__ import annotations

import os

from click.testing import CliRunner

from brain.cli import main


def test_cli_help_lists_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for sub in ("write", "recall", "health", "entity-timeline", "export", "reingest"):
        assert sub in result.output


def test_cli_health_prints_table_counts(pg_url: str) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main, ["health"], env={"BRAIN_DB_URL": pg_url, **os.environ}
    )
    assert result.exit_code == 0
    assert "sources" in result.output
