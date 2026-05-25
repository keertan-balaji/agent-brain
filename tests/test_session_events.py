"""session_events writer."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.hooks.events import record_event
from brain.hooks.session import start_session


def test_record_event_inserts_row(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="ev", cwd="/x", agent="cc", source="startup")
    record_event(engine, session_id=sid, event_kind="user_prompt_submit", payload={"prompt": "hello"})
    with session_scope(engine) as s:
        rows = s.execute(
            text("SELECT event_kind, payload FROM session_events WHERE session_id = :i"),
            {"i": sid},
        ).fetchall()
    assert len(rows) == 1
    assert rows[0].event_kind == "user_prompt_submit"
    assert rows[0].payload == {"prompt": "hello"}


def test_record_event_rejects_bad_kind(pg_url: str) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="bad", cwd="/x", agent="cc", source="startup")
    with pytest.raises(IntegrityError):
        record_event(engine, session_id=sid, event_kind="bogus_kind", payload={})


def test_record_event_default_payload_is_empty_dict(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="def", cwd="/x", agent="cc", source="startup")
    record_event(engine, session_id=sid, event_kind="stop")
    with session_scope(engine) as s:
        payload = s.execute(
            text("SELECT payload FROM session_events WHERE session_id = :i"), {"i": sid}
        ).scalar()
    assert payload == {}
