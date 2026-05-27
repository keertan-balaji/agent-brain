"""Compliance helpers (Phase 3a-4).

Three teeth (spec §Compliance):
1. session_capture_stats + is_under_captured — surface non-capture.
2. is_thin_bundle — surface near-empty resume bundles.
3. is_strict_mode — gate the SessionEnd hook's non-zero exit.

Pure: SQL aggregation + dataclass predicates. No I/O outside the supplied engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.hooks.bundle import BundleSelection


_CAPTURE_KINDS: frozenset[str] = frozenset({
    "decision", "gotcha", "pattern", "note", "subtask_summary", "session_summary"
})


@dataclass(frozen=True)
class CaptureStats:
    session_id: int
    cc_session_id: str | None
    project_id: int | None
    turn_count: int
    capture_count: int
    decision_count: int
    gotcha_count: int
    subtask_summary_count: int
    failure_count: int


def session_capture_stats(engine: Engine, *, session_id: int) -> CaptureStats:
    """Aggregate per-session capture counts in a single round-trip."""
    sql = text(
        """
        SELECT
          sess.id AS sid,
          sess.cc_session_id,
          sess.project_id,
          (SELECT COUNT(*) FROM session_events
             WHERE session_id = sess.id AND event_kind = 'user_prompt_submit') AS turn_count,
          (SELECT COUNT(*) FROM sources s
             WHERE s.kind = ANY(:capture_kinds)
               AND s.project_id IS NOT DISTINCT FROM sess.project_id
               AND s.created_at >= sess.started_at
               AND s.created_at < COALESCE(sess.ended_at, NOW())) AS capture_count,
          (SELECT COUNT(*) FROM sources s
             WHERE s.kind = 'decision'
               AND s.project_id IS NOT DISTINCT FROM sess.project_id
               AND s.created_at >= sess.started_at
               AND s.created_at < COALESCE(sess.ended_at, NOW())) AS decision_count,
          (SELECT COUNT(*) FROM sources s
             WHERE s.kind = 'gotcha'
               AND s.project_id IS NOT DISTINCT FROM sess.project_id
               AND s.created_at >= sess.started_at
               AND s.created_at < COALESCE(sess.ended_at, NOW())) AS gotcha_count,
          (SELECT COUNT(*) FROM sources s
             WHERE s.kind = 'subtask_summary'
               AND s.project_id IS NOT DISTINCT FROM sess.project_id
               AND s.created_at >= sess.started_at
               AND s.created_at < COALESCE(sess.ended_at, NOW())) AS subtask_summary_count,
          (SELECT COUNT(*) FROM failure_memories fm
             WHERE fm.project_id IS NOT DISTINCT FROM sess.project_id
               AND fm.first_attempted_at >= sess.started_at
               AND fm.first_attempted_at < COALESCE(sess.ended_at, NOW())) AS failure_count
        FROM sessions sess
        WHERE sess.id = :sid
        """
    )
    with session_scope(engine) as s:
        row = s.execute(
            sql, {"capture_kinds": list(_CAPTURE_KINDS), "sid": session_id}
        ).first()
    if row is None:
        raise ValueError(f"session {session_id} not found")
    return CaptureStats(
        session_id=row.sid,
        cc_session_id=row.cc_session_id,
        project_id=row.project_id,
        turn_count=int(row.turn_count),
        capture_count=int(row.capture_count),
        decision_count=int(row.decision_count),
        gotcha_count=int(row.gotcha_count),
        subtask_summary_count=int(row.subtask_summary_count),
        failure_count=int(row.failure_count),
    )


def is_under_captured(
    stats: CaptureStats,
    *,
    turn_threshold: int = 5,
    capture_threshold: int = 3,
) -> bool:
    """Sessions below the turn threshold are exploratory, not under-captured."""
    return stats.turn_count >= turn_threshold and stats.capture_count < capture_threshold


def is_thin_bundle(selection: BundleSelection) -> bool:
    """A bundle is thin when no substantive content survives compaction."""
    return (
        not selection.decisions
        and not selection.gotchas
        and not selection.failures
        and not selection.subtasks_open
    )


def under_captured_sessions(
    engine: Engine,
    *,
    turn_threshold: int = 5,
    capture_threshold: int = 3,
    since: datetime | None = None,
    limit: int = 50,
) -> list[CaptureStats]:
    """Audit query: ended sessions matching the under-captured predicate."""
    since_clause = "AND sess.ended_at >= :since" if since is not None else ""
    sql = text(
        f"""
        WITH per_session AS (
          SELECT
            sess.id AS sid,
            sess.cc_session_id,
            sess.project_id,
            sess.started_at,
            sess.ended_at,
            (SELECT COUNT(*) FROM session_events
               WHERE session_id = sess.id AND event_kind = 'user_prompt_submit') AS tc,
            (SELECT COUNT(*) FROM sources s
               WHERE s.kind = ANY(:kinds)
                 AND s.project_id IS NOT DISTINCT FROM sess.project_id
                 AND s.created_at >= sess.started_at
                 AND s.created_at < COALESCE(sess.ended_at, NOW())) AS cc
          FROM sessions sess
          WHERE sess.ended_at IS NOT NULL
            {since_clause}
        )
        SELECT sid, cc_session_id, project_id, tc, cc
        FROM per_session
        WHERE tc >= :turn_t AND cc < :cap_t
        ORDER BY sid DESC
        LIMIT :lim
        """
    )
    params: dict = {
        "kinds": list(_CAPTURE_KINDS),
        "turn_t": turn_threshold,
        "cap_t": capture_threshold,
        "lim": limit,
    }
    if since is not None:
        params["since"] = since
    with session_scope(engine) as s:
        rows = s.execute(sql, params).all()
    return [
        CaptureStats(
            session_id=r.sid,
            cc_session_id=r.cc_session_id,
            project_id=r.project_id,
            turn_count=int(r.tc),
            capture_count=int(r.cc),
            decision_count=0,
            gotcha_count=0,
            subtask_summary_count=0,
            failure_count=0,
        )
        for r in rows
    ]


def is_strict_mode(engine: Engine) -> bool:
    """Read brain_config WHERE key='strict_mode'. Literal string compare against 'true'."""
    with session_scope(engine) as s:
        val = s.execute(
            text("SELECT value FROM brain_config WHERE key = 'strict_mode'")
        ).scalar()
    return val == "true"
