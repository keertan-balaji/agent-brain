"""Session row lifecycle: idempotent start/end keyed on Claude Code's session UUID."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, text

from brain.db import session_scope


def find_session_by_cc_id(engine: Engine, cc_session_id: str) -> int | None:
    """Return the brain `sessions.id` for a given Claude Code session UUID, or None."""
    with session_scope(engine) as s:
        return s.execute(
            text("SELECT id FROM sessions WHERE cc_session_id = :cc"),
            {"cc": cc_session_id},
        ).scalar()


def start_session(
    engine: Engine,
    *,
    cc_session_id: str,
    cwd: str,
    agent: str,
    source: str,
) -> int:
    """Idempotent — if a row with this cc_session_id exists, return it.

    Otherwise insert a new row and return its id. `source` is recorded as the
    initial session_events row in caller code (events module); session itself
    only tracks the immutable identity (cc id, cwd, agent, started_at).
    """
    existing = find_session_by_cc_id(engine, cc_session_id)
    if existing is not None:
        return existing
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(cc_session_id, cwd, agent) "
                "VALUES (:cc, :cwd, :agent) RETURNING id"
            ),
            {"cc": cc_session_id, "cwd": cwd, "agent": agent},
        ).scalar()
    assert sid is not None
    return sid


def end_session(engine: Engine, *, cc_session_id: str, reason: str | None = None) -> None:
    """Mark the session as ended. No-op if the cc_session_id is unknown."""
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        s.execute(
            text("UPDATE sessions SET ended_at = :now WHERE cc_session_id = :cc AND ended_at IS NULL"),
            {"now": now, "cc": cc_session_id},
        )
