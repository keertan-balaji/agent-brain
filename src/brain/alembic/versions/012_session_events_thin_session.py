"""Extend session_events_kind_check to allow 'thin_session' event kind (Phase 3a-4).

Revision ID: 012_events_thin_session
Revises: 011_events_under_captured
"""

from __future__ import annotations

from alembic import op

revision = "012_events_thin_session"
down_revision = "011_events_under_captured"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("session_events_kind_check", "session_events", type_="check")
    op.create_check_constraint(
        "session_events_kind_check",
        "session_events",
        "event_kind IN ('session_start','session_end','user_prompt_submit','stop',"
        "'pre_compact','hook_error','under_captured','thin_session')",
    )


def downgrade() -> None:
    op.drop_constraint("session_events_kind_check", "session_events", type_="check")
    op.create_check_constraint(
        "session_events_kind_check",
        "session_events",
        "event_kind IN ('session_start','session_end','user_prompt_submit','stop',"
        "'pre_compact','hook_error','under_captured')",
    )
