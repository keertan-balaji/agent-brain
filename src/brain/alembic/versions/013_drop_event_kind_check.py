"""Drop session_events_kind_check — open the allowlist so new event kinds
don't require a migration per kind (BUGS.md entry 2026-05-27).

Revision ID: 013_drop_event_kind_check
Revises: 012_events_thin_session
"""

from __future__ import annotations

from alembic import op

revision = "013_drop_event_kind_check"
down_revision = "012_events_thin_session"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("session_events_kind_check", "session_events", type_="check")


def downgrade() -> None:
    # Restore the most-recent allowlist (post-012) so a downgrade is reversible.
    op.create_check_constraint(
        "session_events_kind_check",
        "session_events",
        "event_kind IN ('session_start','session_end','user_prompt_submit','stop',"
        "'pre_compact','hook_error','under_captured','thin_session')",
    )
