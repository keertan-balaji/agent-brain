"""Click sub-group for `brain hook <event>` — dispatches Claude Code hook stdin."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import click
from sqlalchemy import text

from brain.db import session_scope
from brain.hooks.bundle import gather_bundle_selection
from brain.hooks.contracts import (
    PreCompactInput,
    SessionEndInput,
    SessionStartInput,
    StopInput,
    UserPromptSubmitInput,
)
from brain.hooks.events import record_event
from brain.hooks.render import render_bundle
from brain.hooks.session import end_session, start_session


@click.group()
@click.pass_context
def hook(ctx: click.Context) -> None:
    """Claude Code hook dispatcher. Reads stdin JSON, writes session state."""


def _read_stdin_json() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _emit_session_start_output(additional_context: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": additional_context,
        }
    }
    click.echo(json.dumps(payload))


def _emit_empty_output(event_name: str) -> None:
    click.echo(json.dumps({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": ""}}))


def _emit_noop() -> None:
    # Stop / SessionEnd / PreCompact hookSpecificOutput shapes do not accept
    # additionalContext. Emit a minimal valid envelope so the harness schema
    # validator passes.
    click.echo("{}")


@hook.command("session-start")
@click.pass_context
def session_start_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = SessionStartInput.model_validate(raw)
    engine = ctx.obj["engine"]
    sid = start_session(
        engine,
        cc_session_id=inp.session_id,
        cwd=inp.cwd,
        agent="claude-code",
        source=inp.source,
    )
    record_event(
        engine,
        session_id=sid,
        event_kind="session_start",
        payload={"source": inp.source, "model": inp.model, "transcript_path": inp.transcript_path},
    )

    # Atomic claim-and-consume: a single UPDATE with FOR UPDATE SKIP LOCKED on
    # the inner SELECT guarantees that two concurrent SessionStart hooks for the
    # same cwd cannot both consume the same bundle. The losing hook's inner
    # SELECT returns no row (SKIP LOCKED skips the row the winner is updating),
    # so its UPDATE affects zero rows and RETURNING is empty.
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "UPDATE session_resume_bundles "
                "SET consumed_at = :n "
                "WHERE id = ("
                "  SELECT id FROM session_resume_bundles "
                "  WHERE cwd = :c AND consumed_at IS NULL AND superseded_at IS NULL "
                "  ORDER BY generated_at DESC LIMIT 1 "
                "  FOR UPDATE SKIP LOCKED"
                ") "
                "RETURNING rendered"
            ),
            {"n": datetime.now(timezone.utc), "c": inp.cwd},
        ).fetchone()
        if row is None:
            _emit_session_start_output("")
            return
        rendered = row.rendered
    _emit_session_start_output(rendered)


@hook.command("session-end")
@click.pass_context
def session_end_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = SessionEndInput.model_validate(raw)
    engine = ctx.obj["engine"]
    end_session(engine, cc_session_id=inp.session_id, reason=inp.reason)
    with session_scope(engine) as s:
        sid = s.execute(
            text("SELECT id FROM sessions WHERE cc_session_id = :cc"), {"cc": inp.session_id}
        ).scalar()
    if sid is not None:
        record_event(engine, session_id=sid, event_kind="session_end", payload={"reason": inp.reason})
    _emit_noop()


@hook.command("user-prompt-submit")
@click.pass_context
def user_prompt_submit_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = UserPromptSubmitInput.model_validate(raw)
    engine = ctx.obj["engine"]
    sid = start_session(
        engine, cc_session_id=inp.session_id, cwd=inp.cwd, agent="claude-code", source="resume"
    )
    record_event(engine, session_id=sid, event_kind="user_prompt_submit", payload={"prompt": inp.prompt[:1000]})
    _emit_empty_output("UserPromptSubmit")


@hook.command("stop")
@click.pass_context
def stop_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = StopInput.model_validate(raw)
    engine = ctx.obj["engine"]
    sid = start_session(
        engine, cc_session_id=inp.session_id, cwd=inp.cwd, agent="claude-code", source="resume"
    )
    record_event(engine, session_id=sid, event_kind="stop", payload={"stop_hook_active": inp.stop_hook_active})
    _emit_noop()


@hook.command("pre-compact")
@click.pass_context
def pre_compact_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = PreCompactInput.model_validate(raw)
    engine = ctx.obj["engine"]
    sid = start_session(
        engine, cc_session_id=inp.session_id, cwd=inp.cwd, agent="claude-code", source="resume"
    )

    sel = gather_bundle_selection(engine, session_id=sid, cwd=inp.cwd, limit_per_kind=10)
    rendered = render_bundle(
        sel,
        cc_session_id=inp.session_id,
        session_id=sid,
        cwd=inp.cwd,
        trigger="pre_compact",
        token_budget=4000,
        generated_at=datetime.now(timezone.utc),
    )

    # Find or create the project row for this cwd
    with session_scope(engine) as s:
        project_id = s.execute(
            text("SELECT id FROM projects WHERE repo_root = :r"), {"r": inp.cwd}
        ).scalar()
        if project_id is None:
            slug = inp.cwd.rstrip("/").rsplit("/", 1)[-1] or "anon"
            project_id = s.execute(
                text(
                    "INSERT INTO projects(slug, task_type, repo_root) "
                    "VALUES (:s, 'generic', :r) ON CONFLICT (slug) DO UPDATE SET repo_root = EXCLUDED.repo_root "
                    "RETURNING id"
                ),
                {"s": slug, "r": inp.cwd},
            ).scalar()
        s.execute(
            text(
                "UPDATE session_resume_bundles SET superseded_at = NOW() "
                "WHERE cwd = :c AND consumed_at IS NULL AND superseded_at IS NULL"
            ),
            {"c": inp.cwd},
        )
        s.execute(
            text(
                "INSERT INTO session_resume_bundles("
                "project_id, session_id, trigger, token_budget, manifest, rendered, cwd) "
                "VALUES(:p, :s, 'pre_compact', :tb, CAST(:m AS jsonb), :r, :c)"
            ),
            {
                "p": project_id,
                "s": sid,
                "tb": rendered.manifest["token_budget"],
                "m": json.dumps(rendered.manifest),
                "r": rendered.markdown,
                "c": inp.cwd,
            },
        )

    record_event(engine, session_id=sid, event_kind="pre_compact", payload={"trigger": inp.trigger})

    # Stdout becomes "custom compact instructions" — give the compactor a hint.
    click.echo(
        "Compaction note: the brain has persisted a structured resume bundle "
        "for this session. After compaction, the next session's SessionStart "
        "hook will reinject the most recent decisions, gotchas, unresolved "
        "failures, and open subtasks. The compactor may safely shorten chat "
        "scrollback aggressively — durable knowledge is in the brain."
    )
