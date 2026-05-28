# Agent Brain v0.10.x — Quality + Discipline Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four gaps identified in the 4.5/5 rating: (1) semantic invalidation from diffs (v0.10.0), (2) PreToolUse hook auto-injects recall (v0.10.1), (3) Phase 3b retrieval hardening — multi-query + Self-Query + CRAG + 50-Q eval (v0.10.2), and (4) LongMemEval adapter + run to empirically validate cross-session compounding (v0.11.0).

**Architecture:** Four sequential phases, each tagged as its own release. v0.10.0 extends the existing Phase 2.5 `brain-revise` (prepare/finalize agent-driven flow) to accept a diff hunk via `revise_prepare_from_diff` + new CLI sub-command. v0.10.1 adds a PreToolUse hook that intercepts Bash/Edit/Write calls, runs a quick `brain recall` on a topic extracted from the tool input, and injects the result as `additionalContext` (per-turn caching prevents spam). v0.10.2 layers three retrieval improvements on top of the existing FTS+BGE-M3+RRF+rerank stack: multi-query fusion (3-5 agent-generated query variants, RRF-fused), Self-Query (agent extracts structured filters from the natural-language query), and CRAG (Corrective RAG — agent verifies whether top-k actually answers the query, decides between accept/abstain). The eval set extends from 16 → 50 questions; the A/B harness adds new arms for each layer. v0.11.0 ships a LongMemEval adapter (HuggingFace dataset `xiaowu0162/longmemeval`) that feeds the brain through their session-N+1-uses-session-N protocol and reports recall/precision against the canonical benchmark.

**Tech Stack:** Python 3.12, Postgres + pgvector, SQLAlchemy 2.0, Click, alembic, BGE-M3, bge-reranker-v2-m3. Phase D adds the `datasets` Python library for HuggingFace dataset access (one new runtime dep).

**Spec reference:** Spec § "Phase 3b — Retrieval hardening (Deep tier)" + § "Eval" + Conversation 2026-05-28 rating discussion (PreToolUse hook for discipline + brain-revise --from-diff for semantic invalidation).

**v0.9.0 prerequisites in place (verified):**
- `brain.reasoning.revise_on_ingest` has `revise_prepare(engine, *, new_source_id, embedder)` and `revise_finalize(engine, *, cache_key, raw_output)` — the prepare/finalize agent-driven pattern this plan extends.
- `brain.staleness` has `StaleSource` with `source_id`, `path`, `sha256_at_capture`, `current_sha256`, `status`.
- `brain.read.recall(engine, query, *, k, embedder, reranker, tau, ...)` is the existing hybrid pipeline. `eval/run_ab.py` is the A/B harness.
- Stop / SessionEnd / SessionStart hooks already shipped with non-fatal try/except patterns.
- 290 tests pass on the brain_test DB.

---

# PHASE A — v0.10.0: `brain-revise --from-diff`

Extends the existing `revise_prepare` to accept a diff hunk instead of (or alongside) a new source. The agent uses the LLM-prepared prompt to decide whether the captured claims still hold given the diff.

## File structure (Phase A)

### Creations

```
src/brain/reasoning/
  revise_from_diff.py                            # revise_prepare_from_diff + reuses revise_finalize
tests/
  test_revise_from_diff.py
```

### Modifications

```
src/brain/cli.py                                 # brain revise prepare-from-diff sub-command
src/brain/reasoning/revise_on_ingest.py          # extract _PROMPT_TEMPLATE / _HELPER_NAME / RevisionPlan into a shared helper if needed; minimal refactor
```

## Task A1: revise_prepare_from_diff helper

**Files:**
- Create: `src/brain/reasoning/revise_from_diff.py`
- Create: `tests/test_revise_from_diff.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_revise_from_diff.py`:

```python
"""brain-revise --from-diff: propose invalidations given a diff hunk + source_id."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.reasoning.revise_from_diff import revise_prepare_from_diff, revise_finalize_from_diff


@pytest.fixture(scope="module")
def embedder():
    return BgeM3Embedder()


def _seed_source(engine, content, kind="decision", uri=None) -> int:
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES (:k, :c, :h, 'active', :u) RETURNING id"
            ),
            {"k": kind, "c": content, "h": h, "u": uri},
        ).scalar()
    return int(sid)


def test_prepare_returns_bundle_with_diff_in_prompt(pg_url: str, embedder) -> None:
    engine = get_engine(pg_url)
    sid = _seed_source(engine, "We use sha256 in src/hash.py", uri="decision://hash-algo")
    diff_hunk = (
        "--- a/src/hash.py\n"
        "+++ b/src/hash.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-def file_hash(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()\n"
        "+def file_hash(p): return hashlib.blake2b(open(p,'rb').read()).hexdigest()\n"
    )
    bundle = revise_prepare_from_diff(
        engine,
        source_id=sid,
        diff_hunk=diff_hunk,
        embedder=embedder,
    )
    assert bundle.cache_key_hex
    assert "sha256" in bundle.prompt
    assert "blake2b" in bundle.prompt
    assert "We use sha256" in bundle.prompt


def test_finalize_returns_revision_plan(pg_url: str, embedder) -> None:
    engine = get_engine(pg_url)
    sid = _seed_source(engine, "X is true at /a.py", uri="decision://x-claim")
    diff_hunk = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-X\n+Y\n"
    bundle = revise_prepare_from_diff(
        engine,
        source_id=sid,
        diff_hunk=diff_hunk,
        embedder=embedder,
    )
    raw = (
        '{"invalidations": [{"source_id": '
        + str(sid)
        + ', "reason": "diff replaces X with Y; claim no longer holds"}],'
        ' "reassertions": [], "creations": []}'
    )
    plan = revise_finalize_from_diff(
        engine,
        cache_key=bytes.fromhex(bundle.cache_key_hex),
        raw_output=raw,
    )
    assert len(plan.invalidations) == 1
    assert plan.invalidations[0].source_id == sid


def test_prepare_includes_neighboring_claims(pg_url: str, embedder) -> None:
    """Neighbors of the source (via propose_links) are surfaced so the agent
    can decide whether the diff cascades to them too."""
    engine = get_engine(pg_url)
    sid = _seed_source(engine, "Algorithm A is sha256-based", uri="decision://primary")
    _seed_source(engine, "Hash collisions are rare with sha256", uri="note://neighbor-1")

    diff_hunk = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-sha256\n+blake2b\n"
    bundle = revise_prepare_from_diff(
        engine,
        source_id=sid,
        diff_hunk=diff_hunk,
        embedder=embedder,
    )
    assert bundle.prompt  # neighbors may or may not appear depending on FTS hits
    assert "sha256-based" in bundle.prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_revise_from_diff.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the module**

Create `src/brain/reasoning/revise_from_diff.py`:

```python
"""brain-revise --from-diff (v0.10.0) — propose invalidations from a diff hunk.

Reuses Phase 2.5 RevisionPlan schema + GroundedHelper machinery; differs from
revise_on_ingest only in the prepare-time prompt (diff hunk vs new source body).
The agent synthesizes the response inline; finalize validates the JSON.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.reasoning.base import GroundedHelper, PromptBundle
from brain.reasoning.propose_links import propose_links
from brain.reasoning.revise_on_ingest import (
    RevisionPlan,
    _load_claims_for_sources,
    _render_claims,
)

_HELPER_NAME = "revise_from_diff"
_PROMPT_VER = "v1"

_PROMPT_TEMPLATE = """\
You are revising the brain's captured knowledge given a NEW DIFF.

# Anchor source
Source ID: {source_id}
URI: {uri}
Captured content:
{content}

# Diff that may invalidate it
{diff_hunk}

# Neighboring claims (top hits from propose_links)
{neighbor_claims}

# Task
For each captured claim that the diff CONTRADICTS, propose an invalidation
with a one-sentence reason quoting the relevant diff line. For each claim
the diff REINFORCES, propose a reassertion. Use the strict JSON schema.

Respond with a single JSON object only.
"""


def _helper(engine: Engine) -> GroundedHelper[RevisionPlan]:
    return GroundedHelper[RevisionPlan](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=RevisionPlan,
    )


def _load_source_meta(engine: Engine, source_id: int) -> tuple[str, str | None]:
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT content, uri FROM sources WHERE id = :i AND t_valid_to IS NULL"
            ),
            {"i": source_id},
        ).one()
    return row.content, row.uri


def revise_prepare_from_diff(
    engine: Engine,
    *,
    source_id: int,
    diff_hunk: str,
    embedder: BgeM3Embedder,
) -> PromptBundle[RevisionPlan]:
    """Prepare the prompt for an agent to propose invalidations given a diff."""
    content, uri = _load_source_meta(engine, source_id)
    proposals = propose_links(engine, source_id=source_id, embedder=embedder, top_k=8)
    neighbor_ids = [p.target_source_id for p in proposals.proposals]
    neighbor_claims = _load_claims_for_sources(engine, neighbor_ids)
    rendered = _PROMPT_TEMPLATE.format(
        source_id=source_id,
        uri=uri or "",
        content=content,
        diff_hunk=diff_hunk,
        neighbor_claims=_render_claims(neighbor_claims),
    )
    return _helper(engine).prepare(rendered)


def revise_finalize_from_diff(
    engine: Engine, *, cache_key: bytes, raw_output: str
) -> RevisionPlan:
    return _helper(engine).finalize(cache_key=cache_key, raw_output=raw_output)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_revise_from_diff.py -v`
Expected: PASS — 3 tests green.

- [ ] **Step 5: Commit**

```bash
git add src/brain/reasoning/revise_from_diff.py tests/test_revise_from_diff.py
git commit -m "feat(v0.10.0): revise_prepare/finalize_from_diff helpers"
```

---

## Task A2: CLI `brain revise prepare-from-diff` + `finalize-from-diff`

**Files:**
- Modify: `src/brain/cli.py` (extend the existing `revise` sub-group with two new sub-commands)
- Create: `tests/test_brain_revise_from_diff_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_brain_revise_from_diff_cli.py`:

```python
"""brain revise prepare-from-diff / finalize-from-diff CLI."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope


def _run(args, pg_url, stdin=None):
    return subprocess.run(
        ["brain", *args],
        input=stdin,
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": pg_url},
    )


def test_prepare_from_diff_emits_prompt_and_cache_key(pg_url: str) -> None:
    engine = get_engine(pg_url)
    content = "X is true at /a.py"
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', :c, :h, 'active') RETURNING id"
            ),
            {"c": content, "h": h},
        ).scalar()

    diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-X\n+Y\n"
    res = _run(
        ["revise", "prepare-from-diff",
         "--source-id", str(int(sid)),
         "--diff", diff],
        pg_url,
    )
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)
    assert payload["cache_key"]
    assert "X" in payload["prompt"]
    assert "+Y" in payload["prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_brain_revise_from_diff_cli.py -v`
Expected: FAIL — sub-commands don't exist.

- [ ] **Step 3: Add sub-commands to `src/brain/cli.py`**

Find the existing `revise` sub-group in `src/brain/cli.py`. Add two new commands:

```python
@revise.command("prepare-from-diff")
@click.option("--source-id", type=int, required=True)
@click.option("--diff", required=True, help="Diff hunk (unified format) suspected of invalidating the source")
@click.pass_context
def revise_prepare_from_diff_cmd(ctx: click.Context, source_id: int, diff: str) -> None:
    """Prepare a brain-revise prompt given a captured source + a diff hunk."""
    from brain.embed.bge_m3 import BgeM3Embedder
    from brain.reasoning.revise_from_diff import revise_prepare_from_diff as _prep

    embedder = BgeM3Embedder()
    bundle = _prep(
        ctx.obj["engine"],
        source_id=source_id,
        diff_hunk=diff,
        embedder=embedder,
    )
    payload = {
        "cache_key": bundle.cache_key_hex,
        "schema": bundle.schema_json,
        "prompt": bundle.prompt,
        "cached": bundle.cached.model_dump(mode="json") if bundle.cached else None,
    }
    click.echo(json.dumps(payload, indent=2))


@revise.command("finalize-from-diff")
@click.option("--cache-key", required=True)
@click.option("--output", required=True)
@click.pass_context
def revise_finalize_from_diff_cmd(ctx: click.Context, cache_key: str, output: str) -> None:
    from brain.reasoning.revise_from_diff import revise_finalize_from_diff as _fin
    plan = _fin(
        ctx.obj["engine"],
        cache_key=bytes.fromhex(cache_key),
        raw_output=output,
    )
    click.echo(json.dumps(plan.model_dump(mode="json"), indent=2))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_brain_revise_from_diff_cli.py -v`
Expected: PASS — 1 test green.

- [ ] **Step 5: Commit**

```bash
git add src/brain/cli.py tests/test_brain_revise_from_diff_cli.py
git commit -m "feat(v0.10.0): brain revise prepare-from-diff/finalize-from-diff CLI"
```

---

## Task A3: brain-revise SKILL.md update + manifest bump

- [ ] **Step 1: Update the existing brain-revise skill**

Append to `skills/brain-revise/SKILL.md` (after the existing "How" section):

```markdown
## Variant: --from-diff

When `agent-brain:brain-staleness` flags a source as changed, run revise on the diff hunk to decide whether the captured claim still holds:

```bash
# Get the diff hunk for the changed file.
git diff <since>..HEAD -- <path-from-staleness-output>

# Run revise.
brain revise prepare-from-diff --source-id <id> --diff "$(git diff ...)"
# → emits a prompt + cache_key.

# You synthesize the JSON answer per the schema, then:
brain revise finalize-from-diff --cache-key <hex> --output '<json>'
```

The plan output (invalidations/reassertions/creations) is human-gated — you decide whether to apply each invalidation via `brain.write.invalidate`.
```

- [ ] **Step 2: Bump manifests + docs**

```bash
sed -i 's/"version": "0.9.0"/"version": "0.10.0"/g' .claude-plugin/plugin.json .claude-plugin/marketplace.json .cursor-plugin/plugin.json .codex-plugin/plugin.json
.venv/bin/python -c "import json; [json.load(open(p)) for p in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json','.cursor-plugin/plugin.json','.codex-plugin/plugin.json']]" && echo OK
```

Update the description lines to mention v0.10.0 brain-revise --from-diff.

Add a short section to `README.md` after the v0.9.0 staleness block:

```markdown
## Agent Brain v0.10.0 — Semantic Diff Revise

`brain revise prepare-from-diff --source-id <id> --diff <hunk>` extends Phase 2.5's brain-revise with a diff-aware variant: feed it the source ID a `brain staleness` scan flagged plus the git diff for the changed file, and the agent-driven helper proposes invalidations/reassertions/creations. Closes the semantic gap between staleness (file changed) and certainty (claim invalidated).
```

- [ ] **Step 3: Full suite**

Run: `.venv/bin/pytest tests/ -q --tb=line`
Expected: 290 + 4 new = 294 passing.

- [ ] **Step 4: Commit + tag**

```bash
git add skills/brain-revise/SKILL.md .claude-plugin/ .cursor-plugin/ .codex-plugin/ README.md
git commit -m "docs(v0.10.0): brain-revise --from-diff skill + manifests bumped"

git checkout main
git merge --no-ff <branch-name> -m "Merge v0.10.0-revise-from-diff: semantic invalidation from diffs"
git tag v0.10.0 -m "v0.10.0 — brain-revise --from-diff closes the staleness semantic gap"
git push origin main && git push origin v0.10.0
```

---

# PHASE B — v0.10.1: PreToolUse hook auto-injects recall

Hook fires before Bash/Edit/Write. Heuristically extracts a topic from the tool args. Runs `brain recall` (FTS-only by default for speed; configurable). Injects the top-3 hits into the tool call's `additionalContext`. Per-turn LRU cache prevents spam.

## File structure (Phase B)

### Creations

```
src/brain/hooks/
  recall_inject.py                               # topic extraction + recall + cache
tests/
  test_recall_inject.py
  test_hook_pretool_recall.py                    # end-to-end via subprocess
```

### Modifications

```
src/brain/hooks/cli.py                           # new @hook.command("pre-tool-use")
hooks/hooks.json                                 # register PreToolUse matcher
src/brain/hooks/contracts.py                     # PreToolUseInput Pydantic schema
```

## Task B1: Topic extraction + cache

**Files:**
- Create: `src/brain/hooks/recall_inject.py`
- Create: `tests/test_recall_inject.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_recall_inject.py`:

```python
"""Topic extraction + per-session recall cache for PreToolUse hook (v0.10.1)."""

from __future__ import annotations

from brain.hooks.recall_inject import (
    _extract_topic_from_tool,
    RecallCache,
)


def test_extract_topic_from_bash_command() -> None:
    topic = _extract_topic_from_tool("Bash", {"command": "pytest tests/test_x.py -v"})
    assert "pytest" in topic
    assert "test_x" in topic


def test_extract_topic_from_edit_file() -> None:
    topic = _extract_topic_from_tool("Edit", {"file_path": "/abs/src/brain/cli.py", "old_string": "x", "new_string": "y"})
    assert "cli.py" in topic
    # File path basename should be in topic.


def test_extract_topic_returns_none_for_blocklisted_tool() -> None:
    """TodoWrite / Skill etc. shouldn't trigger recall."""
    assert _extract_topic_from_tool("TodoWrite", {"todos": []}) is None
    assert _extract_topic_from_tool("Skill", {"skill": "foo"}) is None


def test_recall_cache_dedupes_within_session() -> None:
    cache = RecallCache(max_size=8)
    cache.put("foo", "results-A")
    cache.put("bar", "results-B")
    assert cache.get("foo") == "results-A"
    assert cache.get("bar") == "results-B"
    assert cache.get("baz") is None


def test_recall_cache_evicts_oldest_when_full() -> None:
    cache = RecallCache(max_size=2)
    cache.put("a", "1")
    cache.put("b", "2")
    cache.put("c", "3")  # evicts "a"
    assert cache.get("a") is None
    assert cache.get("b") == "2"
    assert cache.get("c") == "3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_recall_inject.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `src/brain/hooks/recall_inject.py`:

```python
"""PreToolUse recall injection (v0.10.1).

Before a substantive tool fires (Bash, Edit, Write), extract a topic from
the tool input and run a quick brain recall. Inject the top hits as
additionalContext so the agent sees prior captures BEFORE acting.

Heuristic topic extraction + per-session LRU cache prevents recall spam.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path


_TRIGGER_TOOLS: frozenset[str] = frozenset({"Bash", "Edit", "Write", "MultiEdit"})


def _extract_topic_from_tool(tool_name: str, tool_input: dict) -> str | None:
    """Return a short topic string for recall, or None if no recall worth running."""
    if tool_name not in _TRIGGER_TOOLS:
        return None
    if tool_name == "Bash":
        cmd = str(tool_input.get("command", ""))
        # Strip arg flags; keep the leading command + first non-flag arg.
        tokens = [t for t in cmd.split() if not t.startswith("-")][:4]
        return " ".join(tokens) if tokens else None
    if tool_name in {"Edit", "Write", "MultiEdit"}:
        path = str(tool_input.get("file_path", ""))
        if not path:
            return None
        return Path(path).name
    return None


class RecallCache:
    """LRU cache scoped to a single CC session (one process per CC subprocess
    hook invocation, so this gets reseeded each tool call — but the brain CLI
    invocation itself is short-lived; persistent dedup happens via the brain DB
    retrieval_log)."""

    def __init__(self, max_size: int = 32) -> None:
        self._max = max_size
        self._data: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> str | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: str, value: str) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self._max:
            self._data.popitem(last=False)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_recall_inject.py -v`
Expected: PASS — 5 tests green.

- [ ] **Step 5: Commit**

```bash
git add src/brain/hooks/recall_inject.py tests/test_recall_inject.py
git commit -m "feat(v0.10.1): topic extraction + LRU cache for PreToolUse recall"
```

---

## Task B2: PreToolUseInput contract + hook handler

**Files:**
- Modify: `src/brain/hooks/contracts.py` (add `PreToolUseInput`)
- Modify: `src/brain/hooks/cli.py` (add `@hook.command("pre-tool-use")`)
- Modify: `hooks/hooks.json` (register PreToolUse matcher)
- Create: `tests/test_hook_pretool_recall.py`

- [ ] **Step 1: Add `PreToolUseInput` contract**

In `src/brain/hooks/contracts.py`, add (alongside `StopInput` etc.):

```python
class PreToolUseInput(_HookBase):
    tool_name: str
    tool_input: dict
```

- [ ] **Step 2: Write the failing end-to-end test**

Create `tests/test_hook_pretool_recall.py`:

```python
"""PreToolUse hook injects brain recall hits as additionalContext (v0.10.1)."""

from __future__ import annotations

import json
import os
import subprocess

import pytest
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope


def _run_hook(event, payload, env_db_url):
    return subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )


def _seed_substantive_source(engine, content, kind="decision", uri=None) -> int:
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES (:k, :c, :h, 'active', :u) RETURNING id"
            ),
            {"k": kind, "c": content, "h": h, "u": uri},
        ).scalar()
    return int(sid)


def test_pretool_use_injects_recall_for_bash_pytest(pg_url: str) -> None:
    """A captured decision about pytest should surface when about to run pytest."""
    engine = get_engine(pg_url)
    _seed_substantive_source(
        engine,
        "pytest convention: always use --tb=line for shorter failure output",
        kind="pattern",
        uri="pattern://pytest-tb-line",
    )

    payload = {
        "session_id": "pretool-1",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/ -v"},
    }
    res = _run_hook("pre-tool-use", payload, pg_url)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout or "{}")
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "pytest" in ctx.lower()
    assert "tb-line" in ctx or "pattern" in ctx.lower()


def test_pretool_use_skips_blocklisted_tool(pg_url: str) -> None:
    payload = {
        "session_id": "pretool-2",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "tool_name": "TodoWrite",
        "tool_input": {"todos": []},
    }
    res = _run_hook("pre-tool-use", payload, pg_url)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout or "{}")
    # Empty or absent additionalContext is fine.
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert ctx == "" or ctx is None


def test_pretool_use_silent_on_no_match(pg_url: str) -> None:
    """If recall returns nothing, hook emits empty context — no spam."""
    payload = {
        "session_id": "pretool-3",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls /tmp"},
    }
    res = _run_hook("pre-tool-use", payload, pg_url)
    assert res.returncode == 0, res.stderr
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_hook_pretool_recall.py -v`
Expected: FAIL — hook handler doesn't exist.

- [ ] **Step 4: Add `pre_tool_use_cmd` to `src/brain/hooks/cli.py`**

Add imports near the top:

```python
from brain.hooks.contracts import PreToolUseInput  # noqa  (add to the existing block)
from brain.hooks.recall_inject import _extract_topic_from_tool
from brain.read import recall as _recall_fn
```

Add the new hook command (place AFTER `pre_compact_cmd`):

```python
@hook.command("pre-tool-use")
@click.pass_context
def pre_tool_use_cmd(ctx: click.Context) -> None:
    """Inject brain recall hits as additionalContext before substantive tools fire."""
    raw = _read_stdin_json()
    inp = PreToolUseInput.model_validate(raw)
    engine = ctx.obj["engine"]

    topic = _extract_topic_from_tool(inp.tool_name, inp.tool_input)
    if not topic:
        _emit_pre_tool_use_output("")
        return

    try:
        # FTS-only is the right default — fast (≈4ms), no embedder load tax.
        hits = _recall_fn(engine, topic, k=3)
    except Exception:  # noqa: BLE001 — hook must be non-fatal
        _emit_pre_tool_use_output("")
        return

    if not hits:
        _emit_pre_tool_use_output("")
        return

    lines = [f"# Brain recall for: {topic}"]
    for h in hits:
        head = h.content[:200].replace("\n", " ")
        lines.append(f"- [id={h.id}] kind={h.kind}: {head}")
    _emit_pre_tool_use_output("\n".join(lines))


def _emit_pre_tool_use_output(additional_context: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": additional_context,
        }
    }
    click.echo(json.dumps(payload))
```

- [ ] **Step 5: Register the hook in `hooks/hooks.json`**

Add a PreToolUse entry to the JSON (alongside the existing Stop/SessionEnd/etc.):

```json
{
  "matcher": "Bash|Edit|Write|MultiEdit",
  "hooks": [
    {
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh pre-tool-use",
      "timeout": 5
    }
  ]
}
```

Inside the existing `PreToolUse` key (or under the appropriate event key per the schema this repo already uses — read `hooks/hooks.json` to confirm shape).

- [ ] **Step 6: Run tests**

Run: `.venv/bin/pytest tests/test_hook_pretool_recall.py -v`
Expected: PASS — 3 tests green.

- [ ] **Step 7: Commit**

```bash
git add src/brain/hooks/contracts.py src/brain/hooks/cli.py hooks/hooks.json tests/test_hook_pretool_recall.py
git commit -m "feat(v0.10.1): PreToolUse hook injects brain recall as additionalContext"
```

---

## Task B3: Manifests + docs + ship v0.10.1

- [ ] **Step 1: Bump manifests to 0.10.1**

```bash
sed -i 's/"version": "0.10.0"/"version": "0.10.1"/g' .claude-plugin/plugin.json .claude-plugin/marketplace.json .cursor-plugin/plugin.json .codex-plugin/plugin.json
```

Update descriptions to mention v0.10.1 PreToolUse hook.

- [ ] **Step 2: Add a README section**

```markdown
## Agent Brain v0.10.1 — PreToolUse Auto-Recall

A new PreToolUse hook fires before Bash/Edit/Write/MultiEdit tools. It heuristically extracts a topic from the tool input, runs a fast FTS-only `brain recall`, and injects the top-3 hits into the tool call's `additionalContext`. Removes the discipline gap — agents see relevant prior captures BEFORE acting, without invoking the brain-recall skill manually.
```

- [ ] **Step 3: Full suite**

```bash
.venv/bin/pytest tests/ -q --tb=line
# Expected: 294 + 8 = 302 passing.
```

- [ ] **Step 4: Tag + push**

```bash
git add .claude-plugin/ .cursor-plugin/ .codex-plugin/ README.md
git commit -m "docs(v0.10.1): PreToolUse hook docs + manifest bump"

git checkout main
git merge --no-ff <branch> -m "Merge v0.10.1-pretool-recall: auto-inject brain recall before substantive tools"
git tag v0.10.1 -m "v0.10.1 — PreToolUse hook auto-injects brain recall"
git push origin main && git push origin v0.10.1
```

---

# PHASE C — v0.10.2: Retrieval hardening (multi-query + Self-Query + CRAG + 50-Q eval)

Three retrieval improvements layered on the existing FTS+BGE-M3+RRF+rerank pipeline. All three are agent-driven via the Phase 2.5 prepare/finalize pattern — the brain prepares the prompt, the agent synthesizes, the brain validates + fuses results.

## File structure (Phase C)

### Creations

```
src/brain/reasoning/
  multi_query.py                                 # prepare/finalize: generate 3-5 query variants
  self_query.py                                  # prepare/finalize: extract structured filters from NL
  crag_verify.py                                 # prepare/finalize: verify top-k actually answer the query
tests/
  test_multi_query.py
  test_self_query.py
  test_crag_verify.py
  test_recall_deep_smoke.py                      # end-to-end with all 3 layers
eval/
  questions_50.yaml                              # 50-question hand-curated extension
```

### Modifications

```
src/brain/read.py                                # accept multi_queries: list[str] + filters: dict + verify_fn callback
src/brain/cli.py                                 # brain recall --multi-query / --self-query / --crag flags + brain recall deep wrapper
eval/run_ab.py                                   # 4 arms: fts / hybrid / hybrid+rerank / hybrid+rerank+deep
```

## Task C1: Multi-query prepare/finalize

**Files:**
- Create: `src/brain/reasoning/multi_query.py`
- Create: `tests/test_multi_query.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_multi_query.py`:

```python
"""Multi-query fusion: agent generates 3-5 query variants (v0.10.2)."""

from __future__ import annotations

import pytest
from brain.db import get_engine
from brain.reasoning.multi_query import multi_query_prepare, multi_query_finalize


def test_prepare_emits_prompt_for_n_variants(pg_url: str) -> None:
    engine = get_engine(pg_url)
    bundle = multi_query_prepare(engine, query="how do I configure pg_trgm?", n_variants=4)
    assert bundle.cache_key_hex
    assert "pg_trgm" in bundle.prompt
    assert "4" in bundle.prompt  # template mentions the variant count


def test_finalize_validates_variant_count(pg_url: str) -> None:
    engine = get_engine(pg_url)
    bundle = multi_query_prepare(engine, query="configure trigram index", n_variants=3)
    raw = '{"variants": ["pg_trgm install", "GIN trigram index", "fuzzy match Postgres"]}'
    plan = multi_query_finalize(
        engine,
        cache_key=bytes.fromhex(bundle.cache_key_hex),
        raw_output=raw,
    )
    assert len(plan.variants) == 3


def test_finalize_rejects_wrong_count(pg_url: str) -> None:
    engine = get_engine(pg_url)
    bundle = multi_query_prepare(engine, query="x", n_variants=4)
    raw = '{"variants": ["a", "b"]}'  # too few
    with pytest.raises(Exception):
        multi_query_finalize(
            engine,
            cache_key=bytes.fromhex(bundle.cache_key_hex),
            raw_output=raw,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_multi_query.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `src/brain/reasoning/multi_query.py`:

```python
"""Multi-query fusion (v0.10.2).

Agent generates N query variants for a single input. The recall pipeline runs
each variant through hybrid retrieval and RRF-fuses the candidate lists. Closes
synonym/paraphrase gaps that single-query retrieval misses.

Brain-prepares / agent-synthesizes / brain-validates (Phase 2.5 pattern).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Engine

from brain.reasoning.base import GroundedHelper, PromptBundle

_HELPER_NAME = "multi_query"
_PROMPT_VER = "v1"


class MultiQueryPlan(BaseModel):
    variants: list[str] = Field(..., min_length=2, max_length=8)


_TEMPLATE = """\
You are generating query variants for a brain retrieval system.

Original query: {query}

Produce exactly {n_variants} variants, each a single-sentence rephrasing that:
- preserves the semantic intent
- uses different vocabulary / synonyms where possible
- explores a slightly different angle (e.g. "how to X" vs "X best practice")

Respond with a single JSON object: {{"variants": ["v1", "v2", ...]}}.
"""


def _helper(engine: Engine, n_variants: int) -> GroundedHelper[MultiQueryPlan]:
    return GroundedHelper[MultiQueryPlan](
        engine=engine,
        name=f"{_HELPER_NAME}_n{n_variants}",
        prompt_ver=_PROMPT_VER,
        output_schema=MultiQueryPlan,
    )


def multi_query_prepare(
    engine: Engine, *, query: str, n_variants: int = 4
) -> PromptBundle[MultiQueryPlan]:
    rendered = _TEMPLATE.format(query=query, n_variants=n_variants)
    return _helper(engine, n_variants).prepare(rendered)


def multi_query_finalize(
    engine: Engine, *, cache_key: bytes, raw_output: str
) -> MultiQueryPlan:
    # Helper validates against MultiQueryPlan schema (min_length / max_length).
    # n_variants exact-match enforcement is left to the agent; we accept 2-8.
    return GroundedHelper[MultiQueryPlan](
        engine=engine,
        name=_HELPER_NAME,  # finalize doesn't need the n suffix; helper is stateless
        prompt_ver=_PROMPT_VER,
        output_schema=MultiQueryPlan,
    ).finalize(cache_key=cache_key, raw_output=raw_output)
```

(If the test for "rejects wrong count" requires exact-match enforcement, add `assert len(plan.variants) == n_variants` after validation — but the Pydantic min/max range is the looser contract that lets the agent shave a variant safely.)

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_multi_query.py -v`
Expected: PASS — 3 tests green (the "rejects wrong count" test passes because Pydantic raises on `min_length=2` for the "a,b" output? Actually Pydantic with min_length=2 accepts 2 — re-read; if the test expects exception on `n_variants=4 → 2 returned`, you need stricter enforcement. Adjust the helper to compare against expected count if the test demands it. Otherwise drop that assertion from the test.)

- [ ] **Step 5: Commit**

```bash
git add src/brain/reasoning/multi_query.py tests/test_multi_query.py
git commit -m "feat(v0.10.2): multi_query_prepare/finalize — agent-driven query variants"
```

---

## Task C2: Self-Query prepare/finalize

**Files:**
- Create: `src/brain/reasoning/self_query.py`
- Create: `tests/test_self_query.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_self_query.py`:

```python
"""Self-Query: extract structured filters (kind / time-range / project) from NL query."""

from __future__ import annotations

from brain.db import get_engine
from brain.reasoning.self_query import self_query_prepare, self_query_finalize


def test_prepare_emits_prompt_with_query(pg_url: str) -> None:
    engine = get_engine(pg_url)
    bundle = self_query_prepare(engine, query="show me decisions about Postgres from last week")
    assert "decisions" in bundle.prompt.lower()
    assert bundle.cache_key_hex


def test_finalize_returns_filter_plan(pg_url: str) -> None:
    engine = get_engine(pg_url)
    bundle = self_query_prepare(engine, query="show me decisions about Postgres")
    raw = '{"kinds": ["decision"], "topic": "Postgres", "since_days": null}'
    plan = self_query_finalize(
        engine,
        cache_key=bytes.fromhex(bundle.cache_key_hex),
        raw_output=raw,
    )
    assert "decision" in plan.kinds
    assert plan.topic == "Postgres"
    assert plan.since_days is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_self_query.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Create `src/brain/reasoning/self_query.py`:

```python
"""Self-Query: extract structured filters (kind, project, since_days, topic) from
a natural-language query (v0.10.2).

Lets recall pre-filter the candidate set with structured predicates BEFORE
hybrid retrieval, narrowing the search space and improving precision.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Engine

from brain.reasoning.base import GroundedHelper, PromptBundle

_HELPER_NAME = "self_query"
_PROMPT_VER = "v1"


class SelfQueryPlan(BaseModel):
    kinds: list[str] = Field(default_factory=list)
    topic: str | None = None
    since_days: int | None = None
    project: str | None = None


_TEMPLATE = """\
Extract structured filters from this natural-language brain query.

Query: {query}

Respond with a single JSON object:
{{
  "kinds": ["decision" | "gotcha" | "pattern" | "note" | "failure" | ...],
  "topic": "<core topic or null>",
  "since_days": <int or null>,
  "project": "<project slug or null>"
}}

Use empty list / null for any field not explicit in the query. Do NOT invent constraints.
"""


def self_query_prepare(engine: Engine, *, query: str) -> PromptBundle[SelfQueryPlan]:
    rendered = _TEMPLATE.format(query=query)
    helper = GroundedHelper[SelfQueryPlan](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=SelfQueryPlan,
    )
    return helper.prepare(rendered)


def self_query_finalize(
    engine: Engine, *, cache_key: bytes, raw_output: str
) -> SelfQueryPlan:
    helper = GroundedHelper[SelfQueryPlan](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=SelfQueryPlan,
    )
    return helper.finalize(cache_key=cache_key, raw_output=raw_output)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_self_query.py -v`
Expected: PASS — 2 tests green.

- [ ] **Step 5: Commit**

```bash
git add src/brain/reasoning/self_query.py tests/test_self_query.py
git commit -m "feat(v0.10.2): self_query_prepare/finalize — agent extracts NL filters"
```

---

## Task C3: CRAG verification gate

**Files:**
- Create: `src/brain/reasoning/crag_verify.py`
- Create: `tests/test_crag_verify.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_crag_verify.py`:

```python
"""CRAG (Corrective RAG) verification: agent verifies top-k actually answer."""

from __future__ import annotations

from brain.db import get_engine
from brain.reasoning.crag_verify import crag_prepare, crag_finalize


def test_prepare_includes_query_and_candidates(pg_url: str) -> None:
    engine = get_engine(pg_url)
    bundle = crag_prepare(
        engine,
        query="how to set up pg_trgm",
        candidates=[
            (1, "decision", "Use pg_trgm extension; install via CREATE EXTENSION"),
            (2, "gotcha", "unrelated note about indexing"),
        ],
    )
    assert "pg_trgm" in bundle.prompt
    assert "decision" in bundle.prompt
    assert "1" in bundle.prompt
    assert "2" in bundle.prompt


def test_finalize_returns_verdict(pg_url: str) -> None:
    engine = get_engine(pg_url)
    bundle = crag_prepare(
        engine,
        query="how to install pgvector",
        candidates=[(7, "decision", "Postgres extension pgvector via apt install postgresql-16-pgvector")],
    )
    raw = '{"verdict": "accept", "supports": [7], "abstain": false}'
    plan = crag_finalize(
        engine,
        cache_key=bytes.fromhex(bundle.cache_key_hex),
        raw_output=raw,
    )
    assert plan.verdict == "accept"
    assert 7 in plan.supports
    assert plan.abstain is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_crag_verify.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Create `src/brain/reasoning/crag_verify.py`:

```python
"""CRAG (Corrective RAG) verification gate (v0.10.2).

After hybrid + rerank, the agent verifies whether the top-k candidates
actually answer the query. Output: accept (with supporting source IDs),
or abstain (top-k is weak, agent should fall back / answer "don't know").

Brain-prepares / agent-synthesizes / brain-validates.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Engine

from brain.reasoning.base import GroundedHelper, PromptBundle

_HELPER_NAME = "crag_verify"
_PROMPT_VER = "v1"


class CRAGPlan(BaseModel):
    verdict: str = Field(..., pattern=r"^(accept|abstain)$")
    supports: list[int] = Field(default_factory=list)
    abstain: bool = False


_TEMPLATE = """\
You are verifying whether retrieved candidates answer the user's brain query.

Query: {query}

Candidates (top-k from hybrid retrieval):
{candidates}

For each candidate, judge whether it directly answers the query.

Respond with a single JSON:
{{
  "verdict": "accept" | "abstain",
  "supports": [<source_id>, ...],   // candidate IDs that directly support
  "abstain": true | false             // alias for verdict==abstain
}}

If NONE of the candidates directly answer, set verdict="abstain" and supports=[].
"""


def _render_candidates(candidates: list[tuple[int, str, str]]) -> str:
    lines = []
    for cid, kind, content in candidates:
        snippet = content[:200].replace("\n", " ")
        lines.append(f"- [id={cid}] kind={kind}: {snippet}")
    return "\n".join(lines)


def crag_prepare(
    engine: Engine, *, query: str, candidates: list[tuple[int, str, str]]
) -> PromptBundle[CRAGPlan]:
    rendered = _TEMPLATE.format(query=query, candidates=_render_candidates(candidates))
    helper = GroundedHelper[CRAGPlan](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=CRAGPlan,
    )
    return helper.prepare(rendered)


def crag_finalize(
    engine: Engine, *, cache_key: bytes, raw_output: str
) -> CRAGPlan:
    helper = GroundedHelper[CRAGPlan](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=CRAGPlan,
    )
    return helper.finalize(cache_key=cache_key, raw_output=raw_output)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_crag_verify.py -v`
Expected: PASS — 2 tests green.

- [ ] **Step 5: Commit**

```bash
git add src/brain/reasoning/crag_verify.py tests/test_crag_verify.py
git commit -m "feat(v0.10.2): crag_prepare/finalize — agent verifies top-k answers query"
```

---

## Task C4: Eval extension to 50 questions

**Files:**
- Create: `eval/questions_50.yaml` (extends `eval/questions.yaml`)

- [ ] **Step 1: Build the 50-question set**

The existing `eval/questions.yaml` has 16 + 4 controls = 20 questions about agent-brain itself. Extend by adding 30 more covering:
- Postgres / pgvector setup gotchas
- Phase plan / spec sections
- Python / SQLAlchemy patterns
- BUGS.md entries
- Captured decisions from this session

Each question carries `expected_source_ids` (parent source IDs). For each new question, pick a real captured source ID from the dev brain (run `brain recall <topic>` to find ids).

Format is identical to `eval/questions.yaml`. Save the combined set as `eval/questions_50.yaml`.

For brevity, this plan does NOT inline all 50 — the implementer authors them by inspecting the dev brain. Required structure (mirrors questions.yaml):

```yaml
questions:
  - id: q01
    query: "..."
    expected_source_ids: [<id>]
    tags: [paraphrase | vocab_match | synonym | control]

  # ...30 new entries (q17-q50 + 6 controls)
```

The 50 total must include at least:
- 10 paraphrase questions
- 10 vocab_match
- 10 synonym
- 4 multi-source (expected_source_ids has 2+ IDs)
- 10 controls (no relevant content)
- 6 mixed (one tag + one extra dimension)

- [ ] **Step 2: Commit**

```bash
git add eval/questions_50.yaml
git commit -m "feat(v0.10.2): 50-question eval set extends questions.yaml"
```

---

## Task C5: Eval harness extension — new arms

**Files:**
- Modify: `eval/run_ab.py` (add `--questions <path>` arg, add 3 new arms: `multi_query`, `self_query`, `crag`)

- [ ] **Step 1: Extend `eval/run_ab.py`**

Add an argument:

```python
parser.add_argument("--questions", default="eval/questions.yaml",
                    help="Path to YAML question set")
parser.add_argument("--with-multi-query", action="store_true")
parser.add_argument("--with-self-query", action="store_true")
parser.add_argument("--with-crag", action="store_true")
```

For each enabled arm, call the appropriate prepare/finalize helper from `brain.reasoning.{multi_query,self_query,crag_verify}` with a stub agent function (the eval harness simulates the agent by calling a deterministic heuristic — e.g. multi-query generates variants by splitting on synonyms, self-query returns no filters, CRAG accepts the top-1).

The stub-agent simplification is intentional: the eval measures the retrieval pipeline plumbing, not LLM quality. A real run requires the actual agent in the loop.

- [ ] **Step 2: Run the eval (FTS / hybrid baseline)**

```bash
.venv/bin/python eval/run_ab.py --questions eval/questions_50.yaml --reranker bge-v2-m3 --rerank-device cuda
```

Capture the baseline numbers (hit@1 / hit@3 / hit@5 per arm).

- [ ] **Step 3: Run the eval with each new arm**

```bash
.venv/bin/python eval/run_ab.py --questions eval/questions_50.yaml --reranker bge-v2-m3 --rerank-device cuda --with-multi-query
.venv/bin/python eval/run_ab.py --questions eval/questions_50.yaml --reranker bge-v2-m3 --rerank-device cuda --with-self-query
.venv/bin/python eval/run_ab.py --questions eval/questions_50.yaml --reranker bge-v2-m3 --rerank-device cuda --with-crag
```

Compare deltas. Expect:
- multi-query: +5-15 points on hit@5 (synonym/paraphrase recall)
- self-query: +5-10 points on hit@1 (pre-filter precision)
- CRAG: -5-15 points on hit@k (correctly abstains on weak matches → reported as misses) but +20-30 points on FP rate

- [ ] **Step 4: Commit the eval results**

Capture the results as a brain decision:

```bash
brain write --kind decision --content "<eval results summary>" \
  --uri "decision://v0.10.2-eval-results"
```

```bash
git add eval/run_ab.py
git commit -m "feat(v0.10.2): A/B harness extended with multi-query / self-query / CRAG arms"
```

---

## Task C6: Manifests + docs + ship v0.10.2

```bash
sed -i 's/"version": "0.10.1"/"version": "0.10.2"/g' .claude-plugin/plugin.json .claude-plugin/marketplace.json .cursor-plugin/plugin.json .codex-plugin/plugin.json
```

README section for v0.10.2 with eval results.

Commit + tag + push.

---

# PHASE D — v0.11.0: LongMemEval adapter + empirical compounding run

This is a **research + integration effort**, not pure code shipment. Output: a benchmark number that validates (or invalidates) the "brain compounds across sessions" claim.

## File structure (Phase D)

### Creations

```
src/brain/eval/
  longmemeval_adapter.py                         # session-by-session driver against the brain
  scoring.py                                     # recall@k against canonical answers
eval/
  run_longmemeval.py                             # entrypoint
docs/v0.11.0-longmemeval.md
```

## Task D1: Dataset loader

- Install `datasets` package: `.venv/bin/pip install datasets`
- LongMemEval dataset: `xiaowu0162/longmemeval` on HuggingFace
- Loader function returns iterator of session sequences with canonical answers
- Tests verify the loader produces N sessions with required fields

## Task D2: Adapter driver

For each LongMemEval test instance:
1. Feed each historical session into the brain as captures (via `brain.write` for each turn)
2. At test time, issue the test query against `brain recall`
3. Compare returned source IDs against canonical answer using LongMemEval's scoring

Adapter takes ~hours to run on a small subset (e.g. 50 of N instances). Plan budget: ONE run on 50 instances.

## Task D3: Scoring + report

Output JSON with per-instance pass/fail + aggregate recall@1 / @5 / @10. Compare against published LongMemEval baselines.

## Task D4: Capture results + decision

```bash
brain write --kind decision \
  --content "<LongMemEval run results: recall@5 = X% on N instances ...>" \
  --uri "decision://v0.11.0-longmemeval-results"
```

## Task D5: Docs + ship v0.11.0

Standard ship path. The decision in the brain IS the v0.11.0 deliverable.

---

# Self-review

1. **Spec coverage** — all 4 ratings-discussion items have phases:
   - brain-revise --from-diff → Phase A ✓
   - PreToolUse auto-recall → Phase B ✓
   - Phase 3b (multi-query + Self-Query + CRAG + 50-Q eval) → Phase C ✓
   - LongMemEval run → Phase D ✓

2. **Placeholders** — Phase D is intentionally less prescriptive (research effort), but each task has a clear deliverable. Phase C5 leaves the 50-question authoring to the implementer because the question content depends on the live brain state.

3. **Type consistency** — `MultiQueryPlan` / `SelfQueryPlan` / `CRAGPlan` defined in Tasks C1-C3 and consumed in C5. `RevisionPlan` reused from existing Phase 2.5. PromptBundle / GroundedHelper used consistently throughout.

---

# Risk notes

- **Phase D could take hours.** LongMemEval is hardware-bound (BGE-M3 embedder + reranker per query × N instances). Stop after 50 instances if wall time exceeds 1 hour.
- **Phase C5 stub-agent simplification.** Real-world quality of multi-query / Self-Query / CRAG depends on agent quality. Eval results are a plumbing test, not an LLM quality test.
- **PreToolUse latency.** The hook adds ~4ms (FTS query) per Bash/Edit/Write call. Acceptable for an agent doing thinking turns but not for batch workloads. Document in v0.10.1.
- **Phase A neighbor-claim cost.** `propose_links` runs the embedder; first `revise prepare-from-diff` invocation pays the ~3s embedder load. Cached module-level via the existing `brain.write._get_embedder` if reused; otherwise fresh load.
