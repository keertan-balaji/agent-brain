"""session_events table writer."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, text

from brain.db import session_scope


def record_event(
    engine: Engine,
    *,
    session_id: int,
    event_kind: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Insert a session_events row.

    Raises IntegrityError if event_kind is not in the CHECK constraint
    (session_start | session_end | user_prompt_submit | stop | pre_compact | hook_error).
    """
    body = json.dumps(payload if payload is not None else {})
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO session_events(session_id, event_kind, payload) "
                "VALUES (:sid, :kind, CAST(:p AS jsonb))"
            ),
            {"sid": session_id, "kind": event_kind, "p": body},
        )
