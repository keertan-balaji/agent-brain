"""brain recall wraps high-risk-kind content with origin-aware delimiters."""

from __future__ import annotations

import json
import os
import subprocess

from brain.db import get_engine
from brain.schemas import SourceInput
from brain.write import write


def _run_recall(args: list[str], env_db_url: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["brain", *args],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )
    return result.returncode, result.stdout, result.stderr


def test_recall_wraps_tool_call_output_with_origin_tag(pg_url: str) -> None:
    engine = get_engine(pg_url)
    # Ingest a tool_call_output source with a distinctive token.
    write(
        engine,
        SourceInput(
            kind="tool_call_output",
            content="zzwhalezz traceback bash error",
            uri="test://recall-quoting-1",
        ),
    )
    rc, stdout, stderr = _run_recall(["recall", "zzwhalezz"], pg_url)
    assert rc == 0, stderr
    assert "<tool-output>" in stdout


def test_recall_does_not_wrap_decision_kind(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(
        engine,
        SourceInput(
            kind="decision",
            content="zzdolphinzz we chose Postgres over a dedicated vector DB",
            uri="test://recall-quoting-2",
        ),
    )
    rc, stdout, stderr = _run_recall(["recall", "zzdolphinzz"], pg_url)
    assert rc == 0, stderr
    assert "<tool-output>" not in stdout
    assert "<web-content>" not in stdout
