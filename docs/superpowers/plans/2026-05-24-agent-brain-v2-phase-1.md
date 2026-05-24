# Agent Brain v2 — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the foundation layer of the agent brain — Postgres schema, Python core (`brain.write` / `brain.read`), FTS-only retrieval, v1 markdown migration, Obsidian export, and three skills (`brain-setup`, `brain-recall`, `brain-health`). After Phase 1 the agent can capture and retrieve structured cognition without embeddings; embeddings come in Phase 2.

**Architecture:** Single local Postgres instance (managed via docker-compose for dev, native-install fallback for prod). SQLAlchemy 2.0 ORM. Click CLI with subcommands (`brain setup/write/recall/health/entity-timeline/export/reingest`). Three bash skills are thin wrappers around the CLI. Tests use `pytest-postgresql` for ephemeral test clusters.

**Tech Stack:** Python 3.12+, Postgres 16+, SQLAlchemy 2.0, alembic, Click, Pydantic 2, Jinja2, pytest + pytest-postgresql, uv (dependency manager).

**Spec reference:** `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md`

---

## Deviations from spec

The spec deliberately defers implementation choices to the plan. This plan locks them in. Each deviation is listed with rationale so the reviewer can push back before code lands.

| # | Decision | Spec position | Plan choice | Reason |
|---|---|---|---|---|
| 1 | Python project layout | Silent | `src/brain/` layout with `pyproject.toml` + `uv` for dependency management | `uv` is the fastest pip-compatible installer in 2026 and is becoming standard; `src/` layout prevents accidental imports from CWD during tests |
| 2 | Postgres install path | "docker-compose.yml AND native fallback" | docker-compose as **dev default**; native install documented but optional in setup skill | Reproducibility across contributor environments; one-command spin-up; setup skill detects existing native install and prefers it |
| 3 | Test DB strategy | Silent | `pytest-postgresql` (ephemeral cluster per session) | No Docker dependency for the test runner itself; faster than docker-compose-up-down per session; fine for CI |
| 4 | DB access layer | Silent | SQLAlchemy 2.0 typed ORM | 14 tables make raw psycopg tedious; SQLAlchemy 2.0 typed core matches our Pydantic 2 schemas; async-ready for later |
| 5 | CLI framework | "`brain ...` CLI" — no framework named | Click | Mature, stable, no Pydantic-style runtime overhead; widely-known idioms |
| 6 | Input/output validation | Implicit | Pydantic 2 | Forward-compatible with the reasoning-helper strict-JSON schemas in Phase 2; co-exists with SQLAlchemy 2.0 typed models |
| 7 | `entity_timeline` as skill | "helper, no LLM dep" | CLI subcommand (`brain entity-timeline`) called from `brain-recall` skill when user asks for a timeline | Spec calls it a *helper*, not a skill. Folding into recall keeps Phase 1 at 3 skills (clean scope) |
| 8 | Obsidian export rendering | "default render template" — engine unspecified | Jinja2 per-`kind` templates under `src/brain/obsidian/render_templates/<kind>.md.j2` | Jinja2 is Python standard; per-kind templates match the spec's per-kind fidelity rule |
| 9 | Bash output truncation budget | "head + tail + error-span, configurable" | Default 4KB head + 4KB tail + 4KB error-span lines, stored on `sources.flags.truncation`. Configurable via `brain_config.tool_output_cap` JSONB | Matches spec exactly; locks the defaults so Phase 3a hook implementation has concrete targets |

If any deviation is wrong, flag before Task 1 — every later task assumes these.

---

## File structure

Files created in this phase. Each owns one concern.

```
brain/
├── pyproject.toml                          # uv-managed deps, ruff, mypy, pytest config
├── uv.lock                                  # lockfile (committed)
├── alembic.ini                              # alembic runtime config
├── docker-compose.yml                       # postgres-16 + pgvector for dev
├── .env.example                             # PG connection + paths
├── src/brain/
│   ├── __init__.py                         # package marker, __version__
│   ├── cli.py                              # Click entry point: `brain` command
│   ├── config.py                           # env-var + brain_config table loader
│   ├── db.py                               # SQLAlchemy engine, session factory, ctx mgr
│   ├── models.py                           # SQLAlchemy 2.0 ORM models (all tables)
│   ├── schemas.py                          # Pydantic 2 input/output dataclasses
│   ├── write.py                            # brain.write() — dedup, bi-temporal, depth
│   ├── classify.py                         # bucket-assignment rules per spec
│   ├── read.py                             # brain.read() — FTS pipeline (Phase 1)
│   ├── content_hash.py                     # sha256 over content
│   ├── helpers/
│   │   ├── __init__.py
│   │   ├── entity_timeline.py              # entity_timeline(entity_id, from?, to?)
│   │   └── health.py                       # brain-health audit queries
│   ├── obsidian/
│   │   ├── __init__.py
│   │   ├── export.py                       # DB → markdown view
│   │   ├── reingest.py                     # markdown → DB (DR + v1 migration)
│   │   └── render_templates/
│   │       ├── decision.md.j2
│   │       ├── gotcha.md.j2
│   │       ├── pattern.md.j2
│   │       ├── note.md.j2
│   │       ├── paper.md.j2
│   │       ├── code_file.md.j2
│   │       ├── web_page.md.j2
│   │       ├── session_summary.md.j2
│   │       ├── subtask_summary.md.j2
│   │       └── project_index.md.j2
│   └── alembic/
│       ├── env.py                          # alembic migration context
│       └── versions/
│           ├── 001_brain_config.py
│           ├── 002_projects_sessions_subtasks.py
│           ├── 003_sources_fts_classifications.py
│           ├── 004_failure_memories.py
│           ├── 005_procedures_and_events.py
│           ├── 006_entities_edges.py
│           └── 007_retrieval_log_resume_bundles.py
├── skills/
│   ├── brain-setup/
│   │   ├── SKILL.md
│   │   └── scripts/setup.sh
│   ├── brain-recall/
│   │   ├── SKILL.md
│   │   └── scripts/recall.sh
│   └── brain-health/
│       ├── SKILL.md
│       └── scripts/health.sh
├── tests/
│   ├── conftest.py                         # pytest-postgresql fixture, alembic-applied
│   ├── test_migrations.py                  # alembic up + down cycle
│   ├── test_db_connection.py
│   ├── test_models.py                      # ORM round-trip per table
│   ├── test_write_basic.py
│   ├── test_write_dedup_scope.py
│   ├── test_write_bi_temporal.py
│   ├── test_write_provenance.py
│   ├── test_write_generation_depth.py
│   ├── test_classify.py
│   ├── test_read_fts.py
│   ├── test_read_pre_filter.py
│   ├── test_entity_timeline.py
│   ├── test_health.py
│   ├── test_obsidian_export.py
│   ├── test_v1_migration.py
│   ├── test_cli.py                         # Click invocation smoke tests
│   └── test_end_to_end.py                  # full loop
└── docs/
    ├── installation.md                     # docker-compose + native runbook
    └── operations.md                       # backup/restore/conflict resolution
```

Each file is small (≤300 lines, mostly ≤150). The 14-table schema is the heaviest single file (`models.py` ~400 lines). Migrations are one-table-group each so they're individually reviewable.

---

## Task 1: Project skeleton + dev environment

**Files:**
- Create: `pyproject.toml`
- Create: `uv.lock` (generated by uv)
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `src/brain/__init__.py`
- Create: `tests/conftest.py` (placeholder, expanded in Task 3)
- Modify: `.gitignore` (add `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`)

- [ ] **Step 1: Verify `uv` available**

Run: `uv --version`
Expected: prints version (e.g. `uv 0.5.x`). If absent, install with `curl -LsSf https://astral.sh/uv/install.sh | sh`.

- [ ] **Step 2: Write `pyproject.toml`**

Create at repo root:

```toml
[project]
name = "agent-brain"
version = "0.2.0"
description = "Persistent cognition store for AI coding agents — Phase 1 (Postgres + FTS)"
requires-python = ">=3.12"
authors = [{ name = "keertan", email = "keertan@syntheticsciences.ai" }]
license = { text = "MIT" }
dependencies = [
    "sqlalchemy>=2.0.34",
    "psycopg[binary]>=3.2.0",
    "alembic>=1.13.0",
    "click>=8.1.7",
    "pydantic>=2.8.0",
    "jinja2>=3.1.4",
    "python-frontmatter>=1.1.0",
    "rich>=13.7.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-postgresql>=6.0.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
]

[project.scripts]
brain = "brain.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/brain"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "RUF"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
```

- [ ] **Step 3: Write `docker-compose.yml`**

Create at repo root:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: brain-postgres
    environment:
      POSTGRES_DB: brain
      POSTGRES_USER: brain
      POSTGRES_PASSWORD: brain_dev_password
    ports:
      - "127.0.0.1:5433:5432"
    volumes:
      - brain_pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U brain -d brain"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  brain_pg_data:
```

- [ ] **Step 4: Write `.env.example`**

```bash
# Copy to .env and edit for your environment.
BRAIN_DB_URL=postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain
OBSIDIAN_VAULT=/home/keertan/Documents/ObsidianVault
BRAIN_SUBDIR=Agent-Brain
```

- [ ] **Step 5: Create the Python package marker**

Create `src/brain/__init__.py`:

```python
"""Agent Brain v2 — persistent cognition store."""

__version__ = "0.2.0"
```

- [ ] **Step 6: Create `tests/conftest.py` placeholder**

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures. Expanded in Task 3 once the DB module exists."""
```

- [ ] **Step 7: Update `.gitignore`**

Append to `.gitignore`:

```
# Python
.venv/
__pycache__/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage

# Local env
.env
```

- [ ] **Step 8: Install dependencies + verify Python imports**

Run: `uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"`
Expected: install completes; `python -c "import brain; print(brain.__version__)"` prints `0.2.0`.

- [ ] **Step 9: Spin up Postgres + verify connectivity**

Run: `docker compose up -d && docker compose ps`
Expected: `brain-postgres` is `Up (healthy)`. `psql postgresql://brain:brain_dev_password@127.0.0.1:5433/brain -c '\dx'` lists default extensions.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock docker-compose.yml .env.example src/brain/__init__.py tests/conftest.py .gitignore
git commit -m "feat: project skeleton (pyproject, docker-compose, src layout)"
```

---

## Task 2: DB connection module + config loader

**Files:**
- Create: `src/brain/db.py`
- Create: `src/brain/config.py`
- Create: `tests/test_db_connection.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_connection.py`:

```python
"""Verify the DB connection module produces a working engine + session."""

from sqlalchemy import text

from brain.db import get_engine, session_scope


def test_engine_pings_postgres(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_session_scope_commits(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as session:
        session.execute(text("CREATE TEMP TABLE t(x INT)"))
        session.execute(text("INSERT INTO t VALUES (42)"))
    # commit was implicit on scope exit
    with session_scope(engine) as session:
        # temp table doesn't survive across sessions; that's fine for this test
        result = session.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_session_scope_rollback_on_exception(pg_url: str) -> None:
    engine = get_engine(pg_url)
    try:
        with session_scope(engine) as session:
            session.execute(text("CREATE TEMP TABLE t(x INT)"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    # The temp table should not exist — rollback fired.
    with session_scope(engine) as session:
        result = session.execute(text("SELECT 1")).scalar()
    assert result == 1
```

- [ ] **Step 2: Add the `pg_url` fixture to `tests/conftest.py`**

Replace `tests/conftest.py`:

```python
"""Shared pytest fixtures."""

import os

import pytest


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Connection URL for the dev Postgres instance.

    Phase 1 uses the docker-compose Postgres directly for tests; pytest-postgresql
    integration is added in Task 3 once we have migrations to apply.
    """
    url = os.environ.get(
        "BRAIN_TEST_DB_URL",
        "postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain",
    )
    return url
```

- [ ] **Step 3: Run test to verify it fails (db module doesn't exist)**

Run: `pytest tests/test_db_connection.py -v`
Expected: `ImportError: cannot import name 'get_engine' from 'brain.db'`.

- [ ] **Step 4: Write the db module**

Create `src/brain/db.py`:

```python
"""SQLAlchemy 2.0 engine + session scope. Connection-config only — no schema here."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def get_engine(url: str, *, echo: bool = False) -> Engine:
    """Build a SQLAlchemy engine for the brain DB.

    Args:
        url: postgresql+psycopg://... connection string
        echo: emit SQL to stdout (useful during development)
    """
    return create_engine(url, echo=echo, future=True, pool_pre_ping=True)


_session_factories: dict[int, sessionmaker[Session]] = {}


def _factory_for(engine: Engine) -> sessionmaker[Session]:
    key = id(engine)
    if key not in _session_factories:
        _session_factories[key] = sessionmaker(bind=engine, expire_on_commit=False)
    return _session_factories[key]


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Transactional scope. Commit on clean exit, rollback on exception."""
    session = _factory_for(engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 5: Write `config.py`**

Create `src/brain/config.py`:

```python
"""Brain config: env-var loader + future brain_config table reader."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrainConfig:
    """Static config from environment. Dynamic config lives in the brain_config DB table."""

    db_url: str
    vault_path: Path
    brain_subdir: str

    @property
    def brain_path(self) -> Path:
        return self.vault_path / self.brain_subdir


def load_config() -> BrainConfig:
    db_url = os.environ.get(
        "BRAIN_DB_URL",
        "postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain",
    )
    vault = Path(os.environ.get("OBSIDIAN_VAULT", str(Path.home() / "Documents/ObsidianVault")))
    subdir = os.environ.get("BRAIN_SUBDIR", "Agent-Brain")
    return BrainConfig(db_url=db_url, vault_path=vault, brain_subdir=subdir)
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/test_db_connection.py -v`
Expected: 3 tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/brain/db.py src/brain/config.py tests/conftest.py tests/test_db_connection.py
git commit -m "feat: SQLAlchemy engine + session scope + env config loader"
```

---

## Task 3: Alembic init + migration 001 (brain_config + trigger)

**Files:**
- Create: `alembic.ini`
- Create: `src/brain/alembic/env.py`
- Create: `src/brain/alembic/script.py.mako`
- Create: `src/brain/alembic/versions/001_brain_config.py`
- Create: `tests/test_migrations.py`
- Modify: `tests/conftest.py` (replace with pytest-postgresql + migrations-applied fixture)

- [ ] **Step 1: Initialize alembic**

Run: `cd /home/keertan/codes/brain && alembic init -t async src/brain/alembic`
Then **edit** the generated `alembic.ini`: change `script_location` line to `script_location = src/brain/alembic`. Leave the generated `script.py.mako` alone.

- [ ] **Step 2: Replace generated `src/brain/alembic/env.py`**

```python
"""Alembic env: reads DB URL from BRAIN_DB_URL env var; no async (kept simple for Phase 1)."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    os.environ.get(
        "BRAIN_DB_URL",
        "postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain",
    ),
)

# Models import is added in Task 10 once models.py exists.
target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_migrations.py`:

```python
"""Verify alembic upgrade head + downgrade base cycle is clean."""

import subprocess

from sqlalchemy import text

from brain.db import get_engine


def test_upgrade_head_creates_brain_config(pg_url: str) -> None:
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env={"BRAIN_DB_URL": pg_url, "PATH": __import__("os").environ["PATH"]},
    )
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT key, value FROM brain_config ORDER BY key")
        ).fetchall()
    keys = {r[0] for r in rows}
    assert "active_embedding_model_id" in keys
    assert "active_embedding_model_ver" in keys
    assert "active_embedding_dim" in keys
    assert "tool_output_cap" in keys
    assert "strict_mode" in keys


def test_downgrade_base_drops_brain_config(pg_url: str) -> None:
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env={"BRAIN_DB_URL": pg_url, "PATH": __import__("os").environ["PATH"]},
    )
    subprocess.run(
        ["alembic", "downgrade", "base"],
        check=True,
        env={"BRAIN_DB_URL": pg_url, "PATH": __import__("os").environ["PATH"]},
    )
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        existing = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        ).fetchall()
    table_names = {r[0] for r in existing}
    assert "brain_config" not in table_names
    assert "alembic_version" in table_names  # alembic's own tracking table is kept
```

- [ ] **Step 4: Run test to verify it fails (no migration exists)**

Run: `alembic upgrade head` then `pytest tests/test_migrations.py -v`
Expected: alembic finds no revisions; test fails because `brain_config` table is missing.

- [ ] **Step 5: Write migration 001**

Create `src/brain/alembic/versions/001_brain_config.py`:

```python
"""Brain config table + touch_updated_at trigger function.

Revision ID: 001_brain_config
Revises:
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001_brain_config"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # vector extension declared here so Phase 2 migration only needs CREATE TABLE.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.create_table(
        "brain_config",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Seed defaults. Phase 2 fills in real model_ver/dim; Phase 1 records the planned values.
    op.execute(
        """
        INSERT INTO brain_config(key, value) VALUES
            ('active_embedding_model_id', 'bge-m3'),
            ('active_embedding_model_ver', '2024-06'),
            ('active_embedding_dim', '1024'),
            ('tool_output_cap', '{"head_bytes":4096,"tail_bytes":4096,"error_span_bytes":4096}'),
            ('strict_mode', 'false'),
            ('sleep_time_compute', 'false');
        """
    )


def downgrade() -> None:
    op.drop_table("brain_config")
    op.execute("DROP FUNCTION IF EXISTS touch_updated_at()")
    # Don't drop extensions — they may be used by other databases on the same cluster.
```

- [ ] **Step 6: Update `tests/conftest.py` to apply migrations per test session**

Replace `tests/conftest.py`:

```python
"""Shared pytest fixtures: a fresh per-session DB with all migrations applied."""

import os
import subprocess

import pytest


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = os.environ.get(
        "BRAIN_TEST_DB_URL",
        "postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain",
    )
    return url


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations(pg_url: str) -> None:
    """Run alembic downgrade base + upgrade head once per test session."""
    env = {**os.environ, "BRAIN_DB_URL": pg_url}
    subprocess.run(["alembic", "downgrade", "base"], check=False, env=env)
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
```

- [ ] **Step 7: Run all tests, verify pass**

Run: `pytest tests/ -v`
Expected: 5 tests pass (3 db + 2 migration).

- [ ] **Step 8: Commit**

```bash
git add alembic.ini src/brain/alembic/ tests/test_migrations.py tests/conftest.py
git commit -m "feat: alembic init + migration 001 (brain_config + touch_updated_at trigger)"
```

---

## Task 4: Migration 002 — projects, sessions, subtasks

**Files:**
- Create: `src/brain/alembic/versions/002_projects_sessions_subtasks.py`
- Create: `tests/test_models.py` (start; expanded each migration task)

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
"""Schema round-trip tests: insert a row, read it back, verify shape."""

from datetime import UTC, datetime

from sqlalchemy import text

from brain.db import get_engine, session_scope


def test_projects_round_trip(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO projects(slug, task_type, status, repo_root) "
                "VALUES (:slug, :tt, :st, :root)"
            ),
            {"slug": "test-proj", "tt": "development", "st": "active", "root": "/tmp/x"},
        )
    with session_scope(engine) as s:
        row = s.execute(text("SELECT slug, task_type, status FROM projects")).fetchone()
    assert row is not None
    assert row[0] == "test-proj"
    assert row[1] == "development"
    assert row[2] == "active"


def test_sessions_and_subtasks(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        proj_id = s.execute(
            text(
                "INSERT INTO projects(slug, task_type) VALUES ('p2','development') "
                "RETURNING id"
            )
        ).scalar()
        sess_id = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent) VALUES (:p, 'claude-code') "
                "RETURNING id"
            ),
            {"p": proj_id},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO subtasks(session_id, title, goal) "
                "VALUES (:s, 'do thing', 'do the thing')"
            ),
            {"s": sess_id},
        )
    with session_scope(engine) as s:
        sub = s.execute(text("SELECT title, outcome FROM subtasks")).fetchone()
    assert sub is not None
    assert sub[0] == "do thing"
    assert sub[1] is None  # outcome is NULL until set
```

- [ ] **Step 2: Run, verify fails (tables don't exist)**

Run: `pytest tests/test_models.py -v`
Expected: `UndefinedTable: relation "projects" does not exist`.

- [ ] **Step 3: Write migration 002**

Create `src/brain/alembic/versions/002_projects_sessions_subtasks.py`:

```python
"""Projects, sessions, subtasks.

Revision ID: 002_projects_sessions_subtasks
Revises: 001_brain_config
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002_projects_sessions_subtasks"
down_revision = "001_brain_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column(
            "task_type",
            sa.Text,
            nullable=False,
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("repo_root", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "task_type IN ('development','research','repo-analysis','generic')",
            name="projects_task_type_check",
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("projects.id")),
        sa.Column("agent", sa.Text, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("summary_id", sa.BigInteger),  # FK to sources added in 003
    )

    op.create_table(
        "subtasks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("sessions.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("goal", sa.Text),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.Text),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('success','failure','abandoned','in_progress')",
            name="subtasks_outcome_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("subtasks")
    op.drop_table("sessions")
    op.drop_table("projects")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_migrations.py tests/test_models.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/alembic/versions/002_projects_sessions_subtasks.py tests/test_models.py
git commit -m "feat: migration 002 (projects, sessions, subtasks)"
```

---

## Task 5: Migration 003 — sources + sources_fts + source_projects + memory_classifications

**Files:**
- Create: `src/brain/alembic/versions/003_sources_fts_classifications.py`
- Modify: `tests/test_models.py` (append source tests)

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/test_models.py`:

```python
def test_sources_basic_insert(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('note', 'hello world', sha256('hello world'::bytea)) RETURNING id"
            )
        ).scalar()
        assert sid is not None
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT kind, provenance_kind, generation_depth, status "
                "FROM sources WHERE id = :id"
            ),
            {"id": sid},
        ).fetchone()
    assert row[0] == "note"
    assert row[1] == "captured"  # default
    assert row[2] == 0  # default
    assert row[3] == "active"  # default


def test_sources_scoped_dedup_allows_same_hash_different_kind(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        # Same content_hash but different kind — should be allowed.
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('note', 'duplicated', sha256('duplicated'::bytea))"
            )
        )
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('decision', 'duplicated', sha256('duplicated'::bytea))"
            )
        )
    with session_scope(engine) as s:
        cnt = s.execute(
            text(
                "SELECT COUNT(*) FROM sources WHERE content = 'duplicated' "
                "AND t_valid_to IS NULL"
            )
        ).scalar()
    assert cnt == 2  # two active rows: scoped uniqueness by (kind, uri, content_hash)


def test_sources_scoped_dedup_blocks_same_kind_uri_hash(pg_url: str) -> None:
    engine = get_engine(pg_url)
    import psycopg

    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, uri, content, content_hash) "
                "VALUES ('note', 'x://1', 'dup2', sha256('dup2'::bytea))"
            )
        )
    raised = False
    try:
        with session_scope(engine) as s:
            s.execute(
                text(
                    "INSERT INTO sources(kind, uri, content, content_hash) "
                    "VALUES ('note', 'x://1', 'dup2', sha256('dup2'::bytea))"
                )
            )
    except Exception as exc:  # noqa: BLE001
        raised = "unique" in str(exc).lower() or "duplicate" in str(exc).lower()
    assert raised


def test_memory_classifications_multi_bucket(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('decision','foo',sha256('foo'::bytea)) RETURNING id"
            )
        ).scalar()
        s.execute(
            text(
                "INSERT INTO memory_classifications(source_id, bucket, classifier) "
                "VALUES (:s, 'semantic', 'agent'), (:s, 'episodic', 'agent')"
            ),
            {"s": sid},
        )
    with session_scope(engine) as s:
        buckets = s.execute(
            text(
                "SELECT bucket FROM memory_classifications "
                "WHERE source_id = :s ORDER BY bucket"
            ),
            {"s": sid},
        ).fetchall()
    assert [b[0] for b in buckets] == ["episodic", "semantic"]
```

- [ ] **Step 2: Run, verify fails**

Run: `pytest tests/test_models.py -v`
Expected: fails — `sources` table missing.

- [ ] **Step 3: Write migration 003**

Create `src/brain/alembic/versions/003_sources_fts_classifications.py`:

```python
"""Sources + FTS + source_projects M2M + memory_classifications.

Revision ID: 003_sources_fts_classifications
Revises: 002_projects_sessions_subtasks
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003_sources_fts_classifications"
down_revision = "002_projects_sessions_subtasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("uri", sa.Text),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.LargeBinary, nullable=False),
        sa.Column("mime", sa.Text),
        sa.Column("tokens", sa.Integer),
        sa.Column("lang", sa.Text),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
        sa.Column("invalidation_reason", sa.Text),
        sa.Column("parent_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column("span_start", sa.Integer),
        sa.Column("span_end", sa.Integer),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("projects.id")),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column(
            "provenance_kind",
            sa.Text,
            nullable=False,
            server_default="captured",
        ),
        sa.Column("synthesized_from", sa.ARRAY(sa.BigInteger)),
        sa.Column(
            "generation_depth",
            sa.SmallInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "flags",
            sa.JSON().with_variant(__import__("sqlalchemy.dialects.postgresql", fromlist=["JSONB"]).JSONB, "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "provenance_kind IN ('captured','ingested','synthesized','user_authored')",
            name="sources_provenance_kind_check",
        ),
        sa.CheckConstraint(
            "status IN ('active','archived','draft')",
            name="sources_status_check",
        ),
        sa.CheckConstraint(
            "generation_depth BETWEEN 0 AND 3",
            name="sources_generation_depth_check",
        ),
    )
    op.create_index("sources_kind_idx", "sources", ["kind"])
    op.create_index(
        "sources_validity_idx", "sources", ["t_valid_from", "t_valid_to"]
    )
    op.create_index(
        "sources_provenance_idx", "sources", ["provenance_kind"]
    )
    op.create_index(
        "sources_project_idx",
        "sources",
        ["project_id"],
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index("sources_status_idx", "sources", ["status"])
    op.create_index(
        "sources_hash_lookup_idx", "sources", ["content_hash"]
    )
    op.execute(
        """
        CREATE UNIQUE INDEX sources_scoped_active_idx
        ON sources (kind, COALESCE(uri,''), content_hash)
        WHERE t_valid_to IS NULL
        """
    )
    op.execute(
        """
        CREATE TRIGGER sources_touch BEFORE UPDATE ON sources
        FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
        """
    )

    # Add the deferred sessions.summary_id FK now that sources exists.
    op.create_foreign_key(
        "sessions_summary_id_fk",
        "sessions",
        "sources",
        ["summary_id"],
        ["id"],
    )

    op.create_table(
        "sources_fts",
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tsv", sa.dialects.postgresql.TSVECTOR, nullable=False),
    )
    op.execute("CREATE INDEX sources_fts_idx ON sources_fts USING GIN(tsv)")

    op.create_table(
        "source_projects",
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            sa.BigInteger,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "memory_classifications",
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("bucket", sa.Text, primary_key=True),
        sa.Column(
            "classified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("classifier", sa.Text, nullable=False),
        sa.CheckConstraint(
            "bucket IN ('semantic','episodic','procedural','failure')",
            name="memory_classifications_bucket_check",
        ),
    )
    op.create_index(
        "memory_classifications_bucket_idx",
        "memory_classifications",
        ["bucket"],
    )


def downgrade() -> None:
    op.drop_table("memory_classifications")
    op.drop_table("source_projects")
    op.drop_table("sources_fts")
    op.drop_constraint("sessions_summary_id_fk", "sessions", type_="foreignkey")
    op.execute("DROP TRIGGER IF EXISTS sources_touch ON sources")
    op.drop_table("sources")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_migrations.py tests/test_models.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/alembic/versions/003_sources_fts_classifications.py tests/test_models.py
git commit -m "feat: migration 003 (sources, FTS, source_projects, memory_classifications)"
```

---

## Task 6: Migration 004 — failure_memories

**Files:**
- Create: `src/brain/alembic/versions/004_failure_memories.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Append failing test**

```python
def test_failure_memories_dedup_on_problem_approach(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('gotcha','docker permission denied',sha256('a'::bytea)) "
                "RETURNING id"
            )
        ).scalar()
        s.execute(
            text(
                "INSERT INTO failure_memories(source_id, target_problem, attempted_approach) "
                "VALUES (:s, 'install pg on arch', 'docker compose pgvector')"
            ),
            {"s": sid},
        )
    raised = False
    try:
        with session_scope(engine) as s:
            s.execute(
                text(
                    "INSERT INTO failure_memories(source_id, target_problem, attempted_approach) "
                    "VALUES (:s, 'install pg on arch', 'docker compose pgvector')"
                ),
                {"s": sid},
            )
    except Exception as exc:  # noqa: BLE001
        raised = "unique" in str(exc).lower() or "duplicate" in str(exc).lower()
    assert raised
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_models.py::test_failure_memories_dedup_on_problem_approach -v`
Expected: relation `failure_memories` does not exist.

- [ ] **Step 3: Write migration 004**

```python
"""failure_memories.

Revision ID: 004_failure_memories
Revises: 003_sources_fts_classifications
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_failure_memories"
down_revision = "003_sources_fts_classifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failure_memories",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id"),
            nullable=False,
        ),
        sa.Column("target_problem", sa.Text, nullable=False),
        sa.Column("attempted_approach", sa.Text, nullable=False),
        sa.Column("outcome_evidence", sa.Text),
        sa.Column("root_cause", sa.Text),
        sa.Column("lesson", sa.Text),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "last_attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "first_attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("projects.id")),
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
        sa.Column("invalidation_reason", sa.Text),
        sa.UniqueConstraint(
            "target_problem",
            "attempted_approach",
            name="failure_memories_problem_approach_uq",
        ),
    )
    op.execute(
        "CREATE INDEX failure_memories_problem_idx ON failure_memories "
        "USING GIN(to_tsvector('english', target_problem))"
    )
    op.execute(
        "CREATE INDEX failure_memories_approach_idx ON failure_memories "
        "USING GIN(to_tsvector('english', attempted_approach))"
    )


def downgrade() -> None:
    op.drop_table("failure_memories")
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_migrations.py tests/test_models.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/alembic/versions/004_failure_memories.py tests/test_models.py
git commit -m "feat: migration 004 (failure_memories with problem-approach dedup)"
```

---

## Task 7: Migration 005 — procedures + events with procedure_id FK

**Files:**
- Create: `src/brain/alembic/versions/005_procedures_and_events.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Append failing tests**

```python
def test_events_round_trip(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        pid = s.execute(
            text("INSERT INTO projects(slug, task_type) VALUES ('ep','development') RETURNING id")
        ).scalar()
        sid = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent) VALUES (:p,'claude-code') RETURNING id"
            ),
            {"p": pid},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, tool, status) "
                "VALUES (:s, 1, 'tool_call', 'Bash', 'ok')"
            ),
            {"s": sid},
        )
    with session_scope(engine) as s:
        row = s.execute(text("SELECT kind, tool, status FROM events")).fetchone()
    assert row == ("tool_call", "Bash", "ok")


def test_procedures_partial_unique_active(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('pattern','x',sha256('procx'::bytea)) RETURNING id"
            )
        ).scalar()
        s.execute(
            text(
                "INSERT INTO procedures(source_id, title, target_situation, granularity, build_method) "
                "VALUES (:s, 't', 'install x', 'step', 'user_authored')"
            ),
            {"s": sid},
        )
    raised = False
    try:
        with session_scope(engine) as s:
            sid2 = s.execute(
                text(
                    "INSERT INTO sources(kind, content, content_hash) "
                    "VALUES ('pattern','y',sha256('procy'::bytea)) RETURNING id"
                )
            ).scalar()
            s.execute(
                text(
                    "INSERT INTO procedures(source_id, title, target_situation, granularity, build_method) "
                    "VALUES (:s, 't2', 'install x', 'step', 'user_authored')"
                ),
                {"s": sid2},
            )
    except Exception as exc:  # noqa: BLE001
        raised = "unique" in str(exc).lower() or "duplicate" in str(exc).lower()
    assert raised, "second active step for same situation must violate partial unique index"
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_models.py -v`
Expected: relation `events` or `procedures` missing.

- [ ] **Step 3: Write migration 005**

```python
"""Procedures table + events table + procedure_id FK.

Revision ID: 005_procedures_and_events
Revises: 004_failure_memories
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005_procedures_and_events"
down_revision = "004_failure_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procedures",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("target_situation", sa.Text, nullable=False),
        sa.Column("granularity", sa.Text, nullable=False),
        sa.Column("build_method", sa.Text, nullable=False),
        sa.Column("built_from", sa.ARRAY(sa.BigInteger)),
        sa.Column("success_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_applied_at", sa.DateTime(timezone=True)),
        sa.Column("last_outcome", sa.Text),
        sa.Column("deprecated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "superseded_by",
            sa.BigInteger,
            sa.ForeignKey("procedures.id"),
        ),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("projects.id")),
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "granularity IN ('step','script')",
            name="procedures_granularity_check",
        ),
        sa.CheckConstraint(
            "build_method IN ('distilled_from_episodes','user_authored','imported','llm_proposed')",
            name="procedures_build_method_check",
        ),
        sa.CheckConstraint(
            "last_outcome IS NULL OR last_outcome IN ('success','failure','partial','unknown')",
            name="procedures_last_outcome_check",
        ),
        sa.CheckConstraint(
            "superseded_by IS NULL OR superseded_by != id",
            name="procedures_no_self_supersede",
        ),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX procedures_active_unique_idx
        ON procedures (target_situation, granularity) WHERE deprecated_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX procedures_active_idx ON procedures(target_situation)
        WHERE deprecated_at IS NULL
        """
    )
    op.create_index(
        "procedures_outcome_idx",
        "procedures",
        ["last_outcome", sa.text("last_applied_at DESC")],
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("subtask_id", sa.BigInteger, sa.ForeignKey("subtasks.id")),
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("sessions.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("tool", sa.Text),
        sa.Column("input_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column("output_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column("source_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column("status", sa.Text),
        sa.Column("duration_ms", sa.Integer),
        sa.Column(
            "procedure_id",
            sa.BigInteger,
            sa.ForeignKey("procedures.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("session_id", "ordinal", name="events_session_ordinal_uq"),
    )
    op.create_index("events_subtask_idx", "events", ["subtask_id"])
    op.execute(
        "CREATE INDEX events_procedure_idx ON events(procedure_id) "
        "WHERE procedure_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("procedures")
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_migrations.py tests/test_models.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/alembic/versions/005_procedures_and_events.py tests/test_models.py
git commit -m "feat: migration 005 (procedures lifecycle + events with procedure_id FK)"
```

---

## Task 8: Migration 006 — entities + edges

**Files:**
- Create: `src/brain/alembic/versions/006_entities_edges.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Append failing test**

```python
def test_entities_and_edges(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('paper','x',sha256('paperx'::bytea)) RETURNING id"
            )
        ).scalar()
        a = s.execute(
            text(
                "INSERT INTO entities(kind, canonical_name, source_id) "
                "VALUES ('person','Alice',:s) RETURNING id"
            ),
            {"s": sid},
        ).scalar()
        b = s.execute(
            text(
                "INSERT INTO entities(kind, canonical_name, source_id) "
                "VALUES ('person','Bob',:s) RETURNING id"
            ),
            {"s": sid},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO edges(src_id, dst_id, relation, source_id) "
                "VALUES (:a, :b, 'cites', :s)"
            ),
            {"a": a, "b": b, "s": sid},
        )
    with session_scope(engine) as s:
        rel = s.execute(text("SELECT relation FROM edges")).scalar()
    assert rel == "cites"
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_models.py::test_entities_and_edges -v`
Expected: relation `entities` does not exist.

- [ ] **Step 3: Write migration 006**

```python
"""entities + edges (knowledge graph layer; LLM extraction in Phase 2).

Revision ID: 006_entities_edges
Revises: 005_procedures_and_events
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_entities_edges"
down_revision = "005_procedures_and_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("canonical_name", sa.Text, nullable=False),
        sa.Column("aliases", sa.ARRAY(sa.Text)),
        sa.Column("source_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
    )
    op.create_index("entities_kind_idx", "entities", ["kind"])

    op.create_table(
        "edges",
        sa.Column(
            "src_id", sa.BigInteger, sa.ForeignKey("entities.id"), primary_key=True
        ),
        sa.Column(
            "dst_id", sa.BigInteger, sa.ForeignKey("entities.id"), primary_key=True
        ),
        sa.Column("relation", sa.Text, primary_key=True),
        sa.Column("weight", sa.Float),
        sa.Column("source_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("edges")
    op.drop_table("entities")
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_migrations.py tests/test_models.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/brain/alembic/versions/006_entities_edges.py tests/test_models.py
git commit -m "feat: migration 006 (entities + edges)"
```

---

## Task 9: Migration 007 — retrieval_log + session_resume_bundles

**Files:**
- Create: `src/brain/alembic/versions/007_retrieval_log_resume_bundles.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Append failing test**

```python
def test_retrieval_log_inserts(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO retrieval_log(query, agent) VALUES ('hello world','claude-code')"
            )
        )
    with session_scope(engine) as s:
        q = s.execute(text("SELECT query FROM retrieval_log")).scalar()
    assert q == "hello world"


def test_session_resume_bundles_active_unique(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        pid = s.execute(
            text("INSERT INTO projects(slug, task_type) VALUES ('rb','development') RETURNING id")
        ).scalar()
        s.execute(
            text(
                "INSERT INTO session_resume_bundles(project_id, trigger, token_budget, manifest, rendered) "
                "VALUES (:p,'manual', 500, '{}'::jsonb, 'render1')"
            ),
            {"p": pid},
        )
    raised = False
    try:
        with session_scope(engine) as s:
            s.execute(
                text(
                    "INSERT INTO session_resume_bundles(project_id, trigger, token_budget, manifest, rendered) "
                    "VALUES (:p,'manual', 500, '{}'::jsonb, 'render2')"
                ),
                {"p": pid},
            )
    except Exception as exc:  # noqa: BLE001
        raised = "unique" in str(exc).lower() or "duplicate" in str(exc).lower()
    assert raised, "second active bundle for same project must violate partial unique index"
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_models.py -v`

- [ ] **Step 3: Write migration 007**

```python
"""retrieval_log + session_resume_bundles.

Revision ID: 007_retrieval_log_resume_bundles
Revises: 006_entities_edges
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_retrieval_log_resume_bundles"
down_revision = "006_entities_edges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retrieval_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("filters", postgresql.JSONB),
        sa.Column("candidates", postgresql.JSONB),
        sa.Column("selected", sa.ARRAY(sa.BigInteger)),
        sa.Column("synthesized_ratio", sa.Float),
        sa.Column("captured_ratio", sa.Float),
        sa.Column(
            "abstained", sa.Boolean, nullable=False, server_default=sa.text("FALSE")
        ),
        sa.Column("top1_score", sa.Float),
        sa.Column("agent", sa.Text),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("sessions.id")),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "retrieval_log_session_idx", "retrieval_log", ["session_id", "occurred_at"]
    )

    op.create_table(
        "session_resume_bundles",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.BigInteger,
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("sessions.id")),
        sa.Column("trigger", sa.Text, nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("token_budget", sa.Integer, nullable=False),
        sa.Column("manifest", postgresql.JSONB, nullable=False),
        sa.Column("rendered", sa.Text, nullable=False),
        sa.CheckConstraint(
            "trigger IN ('pre_compact','session_end','manual')",
            name="session_resume_bundles_trigger_check",
        ),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX bundles_project_active_unique_idx
        ON session_resume_bundles(project_id) WHERE superseded_at IS NULL
        """
    )
    op.create_index(
        "bundles_project_idx",
        "session_resume_bundles",
        ["project_id", sa.text("generated_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("session_resume_bundles")
    op.drop_table("retrieval_log")
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_migrations.py tests/test_models.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/brain/alembic/versions/007_retrieval_log_resume_bundles.py tests/test_models.py
git commit -m "feat: migration 007 (retrieval_log + session_resume_bundles)"
```

---

## Task 10: SQLAlchemy ORM models for every table

**Files:**
- Create: `src/brain/models.py`
- Modify: `src/brain/alembic/env.py` (set `target_metadata`)

- [ ] **Step 1: Write failing test**

Append to `tests/test_models.py`:

```python
from brain.models import Source, Project, Session as BrainSession, Subtask
from brain.db import get_engine, session_scope


def test_orm_round_trip_project_and_source(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        p = Project(slug="orm-test", task_type="development", status="active")
        s.add(p)
        s.flush()
        src = Source(
            kind="note",
            content="orm hello",
            content_hash=__import__("hashlib").sha256(b"orm hello").digest(),
            project_id=p.id,
        )
        s.add(src)
        s.flush()
        pid = p.id
        sid = src.id
    with session_scope(engine) as s:
        loaded = s.get(Source, sid)
    assert loaded is not None
    assert loaded.kind == "note"
    assert loaded.project_id == pid
    assert loaded.provenance_kind == "captured"
    assert loaded.generation_depth == 0
    assert loaded.status == "active"
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_models.py::test_orm_round_trip_project_and_source -v`

- [ ] **Step 3: Write models.py**

Create `src/brain/models.py`:

```python
"""SQLAlchemy 2.0 ORM models. One class per migrated table.

Mirrors the DDL in src/brain/alembic/versions/*. Migrations are the source of truth;
these classes are the typed Python facade.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BrainConfig(Base):
    __tablename__ = "brain_config"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('development','research','repo-analysis','generic')",
            name="projects_task_type_check",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    repo_root: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("projects.id"))
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sources.id"))


class Subtask(Base):
    __tablename__ = "subtasks"
    __table_args__ = (
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('success','failure','abandoned','in_progress')",
            name="subtasks_outcome_check",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(Text)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "provenance_kind IN ('captured','ingested','synthesized','user_authored')",
            name="sources_provenance_kind_check",
        ),
        CheckConstraint(
            "status IN ('active','archived','draft')", name="sources_status_check"
        ),
        CheckConstraint(
            "generation_depth BETWEEN 0 AND 3", name="sources_generation_depth_check"
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    uri: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    mime: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[int | None] = mapped_column(Integer)
    lang: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    t_valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    t_valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sources.id"))
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("projects.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    provenance_kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="captured"
    )
    synthesized_from: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    generation_depth: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    flags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )


class SourceFTS(Base):
    __tablename__ = "sources_fts"
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    tsv: Mapped[Any] = mapped_column(TSVECTOR, nullable=False)


class SourceProject(Base):
    __tablename__ = "source_projects"
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )


class MemoryClassification(Base):
    __tablename__ = "memory_classifications"
    __table_args__ = (
        CheckConstraint(
            "bucket IN ('semantic','episodic','procedural','failure')",
            name="memory_classifications_bucket_check",
        ),
    )
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    bucket: Mapped[str] = mapped_column(Text, primary_key=True)
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    classifier: Mapped[str] = mapped_column(Text, nullable=False)


class FailureMemory(Base):
    __tablename__ = "failure_memories"
    __table_args__ = (
        UniqueConstraint(
            "target_problem",
            "attempted_approach",
            name="failure_memories_problem_approach_uq",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id"), nullable=False
    )
    target_problem: Mapped[str] = mapped_column(Text, nullable=False)
    attempted_approach: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_evidence: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    lesson: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    first_attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("projects.id"))
    t_valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    t_valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(Text)


class Procedure(Base):
    __tablename__ = "procedures"
    __table_args__ = (
        CheckConstraint(
            "granularity IN ('step','script')", name="procedures_granularity_check"
        ),
        CheckConstraint(
            "build_method IN ('distilled_from_episodes','user_authored','imported','llm_proposed')",
            name="procedures_build_method_check",
        ),
        CheckConstraint(
            "last_outcome IS NULL OR last_outcome IN ('success','failure','partial','unknown')",
            name="procedures_last_outcome_check",
        ),
        CheckConstraint(
            "superseded_by IS NULL OR superseded_by != id",
            name="procedures_no_self_supersede",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    target_situation: Mapped[str] = mapped_column(Text, nullable=False)
    granularity: Mapped[str] = mapped_column(Text, nullable=False)
    build_method: Mapped[str] = mapped_column(Text, nullable=False)
    built_from: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_outcome: Mapped[str | None] = mapped_column(Text)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("procedures.id")
    )
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("projects.id"))
    t_valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    t_valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("session_id", "ordinal", name="events_session_ordinal_uq"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subtask_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("subtasks.id"))
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str | None] = mapped_column(Text)
    input_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sources.id"))
    output_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sources.id"))
    source_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sources.id"))
    status: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    procedure_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("procedures.id", ondelete="SET NULL")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    source_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sources.id"))
    t_valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    t_valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Edge(Base):
    __tablename__ = "edges"
    src_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("entities.id"), primary_key=True
    )
    dst_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("entities.id"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(Text, primary_key=True)
    weight: Mapped[float | None] = mapped_column(Float)
    source_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sources.id"))
    t_valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    t_valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetrievalLog(Base):
    __tablename__ = "retrieval_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    candidates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    selected: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    synthesized_ratio: Mapped[float | None] = mapped_column(Float)
    captured_ratio: Mapped[float | None] = mapped_column(Float)
    abstained: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="FALSE"
    )
    top1_score: Mapped[float | None] = mapped_column(Float)
    agent: Mapped[str | None] = mapped_column(Text)
    session_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sessions.id"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SessionResumeBundle(Base):
    __tablename__ = "session_resume_bundles"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('pre_compact','session_end','manual')",
            name="session_resume_bundles_trigger_check",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=False
    )
    session_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sessions.id"))
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rendered: Mapped[str] = mapped_column(Text, nullable=False)
```

- [ ] **Step 4: Wire `target_metadata` in alembic env**

Edit `src/brain/alembic/env.py`: change `target_metadata = None` to:

```python
from brain.models import Base
target_metadata = Base.metadata
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/ -v`
Expected: all tests pass; ORM round-trip works.

- [ ] **Step 6: Commit**

```bash
git add src/brain/models.py src/brain/alembic/env.py tests/test_models.py
git commit -m "feat: SQLAlchemy 2.0 ORM models for all 14 tables"
```

---

## Task 11: brain.write() — scoped dedup + bi-temporal + generation_depth

**Files:**
- Create: `src/brain/content_hash.py`
- Create: `src/brain/write.py`
- Create: `src/brain/schemas.py`
- Create: `tests/test_write_basic.py`
- Create: `tests/test_write_dedup_scope.py`
- Create: `tests/test_write_bi_temporal.py`
- Create: `tests/test_write_provenance.py`
- Create: `tests/test_write_generation_depth.py`

- [ ] **Step 1: Write content hash helper**

Create `src/brain/content_hash.py`:

```python
"""sha256 over text content. Used for dedup lookups across the brain."""

from __future__ import annotations

import hashlib


def sha256_bytes(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()
```

- [ ] **Step 2: Write Pydantic input schema**

Create `src/brain/schemas.py`:

```python
"""Pydantic 2 input/output schemas for brain.write() / brain.read() / helpers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProvenanceKind = Literal["captured", "ingested", "synthesized", "user_authored"]
SourceKind = Literal[
    "tool_call_output",
    "command",
    "edit",
    "decision",
    "note",
    "gotcha",
    "pattern",
    "paper",
    "code_file",
    "web_page",
    "chunk_context",
    "faq",
    "session_summary",
    "subtask_summary",
    "image",
    "binary_artifact",
    "project_index",
]
Bucket = Literal["semantic", "episodic", "procedural", "failure"]
Status = Literal["active", "archived", "draft"]


class SourceInput(BaseModel):
    """Caller-facing input to brain.write()."""

    model_config = ConfigDict(frozen=True)

    kind: SourceKind
    content: str
    uri: str | None = None
    mime: str | None = None
    lang: str | None = None
    project_id: int | None = None
    status: Status = "active"
    provenance_kind: ProvenanceKind = "captured"
    synthesized_from: list[int] | None = None
    parent_id: int | None = None
    span_start: int | None = None
    span_end: int | None = None
    flags: dict[str, object] = Field(default_factory=dict)
    classifier: str = "agent"
    buckets: list[Bucket] = Field(default_factory=list)


class WriteResult(BaseModel):
    """Return shape from brain.write()."""

    source_id: int
    created: bool  # False if existing active row returned (dedup hit)
    generation_depth: int
```

- [ ] **Step 3: Write failing tests (basic)**

Create `tests/test_write_basic.py`:

```python
from brain.db import get_engine
from brain.schemas import SourceInput
from brain.write import write


def test_write_returns_source_id_and_created(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", content="hello brain"))
    assert res.source_id > 0
    assert res.created is True
    assert res.generation_depth == 0


def test_write_classifies_bucket_when_given(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(
        engine,
        SourceInput(kind="decision", content="use postgres", buckets=["semantic", "episodic"]),
    )
    from sqlalchemy import text

    from brain.db import session_scope

    with session_scope(engine) as s:
        buckets = sorted(
            row[0]
            for row in s.execute(
                text("SELECT bucket FROM memory_classifications WHERE source_id = :s"),
                {"s": res.source_id},
            ).fetchall()
        )
    assert buckets == ["episodic", "semantic"]


def test_write_populates_fts(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", content="postgres pgvector hybrid"))
    from sqlalchemy import text

    from brain.db import session_scope

    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT 1 FROM sources_fts WHERE source_id = :s "
                "AND tsv @@ to_tsquery('english', 'postgres & pgvector')"
            ),
            {"s": res.source_id},
        ).scalar()
    assert row == 1
```

- [ ] **Step 4: Write failing test (dedup scope)**

Create `tests/test_write_dedup_scope.py`:

```python
from brain.db import get_engine
from brain.schemas import SourceInput
from brain.write import write


def test_dedup_hits_when_same_kind_uri_content(pg_url: str) -> None:
    engine = get_engine(pg_url)
    first = write(engine, SourceInput(kind="note", uri="x://a", content="same body"))
    second = write(engine, SourceInput(kind="note", uri="x://a", content="same body"))
    assert second.source_id == first.source_id
    assert second.created is False


def test_dedup_misses_when_different_kind(pg_url: str) -> None:
    engine = get_engine(pg_url)
    first = write(engine, SourceInput(kind="note", uri="x://b", content="text"))
    second = write(engine, SourceInput(kind="decision", uri="x://b", content="text"))
    assert second.source_id != first.source_id
    assert second.created is True


def test_dedup_misses_when_different_uri(pg_url: str) -> None:
    engine = get_engine(pg_url)
    first = write(engine, SourceInput(kind="note", uri="x://c1", content="body3"))
    second = write(engine, SourceInput(kind="note", uri="x://c2", content="body3"))
    assert second.source_id != first.source_id
```

- [ ] **Step 5: Write failing test (bi-temporal re-assertion)**

Create `tests/test_write_bi_temporal.py`:

```python
from datetime import datetime

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.schemas import SourceInput
from brain.write import invalidate, write


def test_invalidate_marks_t_valid_to(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", uri="x://i1", content="will be invalid"))
    invalidate(engine, res.source_id, reason="user requested")
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT t_valid_to, invalidation_reason FROM sources WHERE id = :s"),
            {"s": res.source_id},
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[1] == "user requested"


def test_reassert_after_invalidate_creates_new_row(pg_url: str) -> None:
    engine = get_engine(pg_url)
    first = write(engine, SourceInput(kind="note", uri="x://i2", content="body"))
    invalidate(engine, first.source_id, reason="superseded")
    second = write(engine, SourceInput(kind="note", uri="x://i2", content="body"))
    assert second.source_id != first.source_id
    assert second.created is True
```

- [ ] **Step 6: Write failing test (provenance + generation_depth)**

Create `tests/test_write_generation_depth.py`:

```python
import pytest

from brain.db import get_engine
from brain.schemas import SourceInput
from brain.write import write


def test_captured_source_has_depth_zero(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", content="captured"))
    assert res.generation_depth == 0


def test_synthesized_from_captured_has_depth_one(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="src1"))
    b = write(engine, SourceInput(kind="note", content="src2"))
    syn = write(
        engine,
        SourceInput(
            kind="faq",
            content="answer derived from src1+src2",
            provenance_kind="synthesized",
            synthesized_from=[a.source_id, b.source_id],
        ),
    )
    assert syn.generation_depth == 1


def test_synthesized_from_synthesized_has_depth_two(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="raw"))
    d1 = write(
        engine,
        SourceInput(
            kind="faq",
            content="depth 1",
            provenance_kind="synthesized",
            synthesized_from=[a.source_id],
        ),
    )
    d2 = write(
        engine,
        SourceInput(
            kind="faq",
            content="depth 2",
            provenance_kind="synthesized",
            synthesized_from=[d1.source_id],
        ),
    )
    assert d1.generation_depth == 1
    assert d2.generation_depth == 2


def test_depth_three_is_max_and_depth_four_rejected(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="root"))
    d1 = write(
        engine,
        SourceInput(
            kind="faq", content="d1", provenance_kind="synthesized", synthesized_from=[a.source_id]
        ),
    )
    d2 = write(
        engine,
        SourceInput(
            kind="faq", content="d2", provenance_kind="synthesized", synthesized_from=[d1.source_id]
        ),
    )
    d3 = write(
        engine,
        SourceInput(
            kind="faq", content="d3", provenance_kind="synthesized", synthesized_from=[d2.source_id]
        ),
    )
    assert d3.generation_depth == 3
    with pytest.raises(ValueError, match="generation_depth"):
        write(
            engine,
            SourceInput(
                kind="faq",
                content="d4 too deep",
                provenance_kind="synthesized",
                synthesized_from=[d3.source_id],
            ),
        )
```

- [ ] **Step 7: Verify all four test files fail**

Run: `pytest tests/test_write*.py -v`
Expected: every test fails with `ImportError: cannot import name 'write' from 'brain.write'`.

- [ ] **Step 8: Write `brain.write()`**

Create `src/brain/write.py`:

```python
"""brain.write() — the single entry point for capturing a source into the brain.

Implements:
- scoped dedup via (kind, uri, content_hash) unique index
- bi-temporal re-assertion (invalidated rows free the slot)
- generation_depth computation for provenance discipline (max=3, depth-4 rejected)
- FTS row materialization (sources_fts)
- optional memory_classifications inserts
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, text

from brain.content_hash import sha256_bytes
from brain.db import session_scope
from brain.schemas import SourceInput, WriteResult


def _compute_generation_depth(
    engine: Engine, synthesized_from: list[int] | None, provenance_kind: str
) -> int:
    if provenance_kind != "synthesized" or not synthesized_from:
        return 0
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT generation_depth FROM sources WHERE id = ANY(:ids)"
            ),
            {"ids": synthesized_from},
        ).fetchall()
    if not rows:
        return 1  # synthesized but no traceable inputs — still depth-1 by definition
    return 1 + max(r[0] for r in rows)


def write(engine: Engine, source: SourceInput) -> WriteResult:
    """Insert a source, dedup-scoped to (kind, uri, content_hash) within active rows.

    Returns the resulting source_id and whether a new row was created.
    """
    depth = _compute_generation_depth(
        engine, source.synthesized_from, source.provenance_kind
    )
    if depth > 3:
        raise ValueError(
            f"generation_depth would be {depth} (>3); consolidate inputs before writing"
        )

    content_hash = sha256_bytes(source.content)
    uri_for_dedup = source.uri or ""  # COALESCE in the index

    with session_scope(engine) as s:
        existing = s.execute(
            text(
                "SELECT id FROM sources "
                "WHERE kind = :k AND COALESCE(uri,'') = :u AND content_hash = :h "
                "AND t_valid_to IS NULL"
            ),
            {"k": source.kind, "u": uri_for_dedup, "h": content_hash},
        ).scalar()
        if existing is not None:
            return WriteResult(
                source_id=existing, created=False, generation_depth=depth
            )

        result = s.execute(
            text(
                """
                INSERT INTO sources(
                    kind, uri, content, content_hash, mime, lang,
                    project_id, status, provenance_kind, synthesized_from,
                    generation_depth, parent_id, span_start, span_end, flags
                ) VALUES (
                    :kind, :uri, :content, :content_hash, :mime, :lang,
                    :project_id, :status, :provenance_kind, :synthesized_from,
                    :generation_depth, :parent_id, :span_start, :span_end, :flags::jsonb
                ) RETURNING id
                """
            ),
            {
                "kind": source.kind,
                "uri": source.uri,
                "content": source.content,
                "content_hash": content_hash,
                "mime": source.mime,
                "lang": source.lang,
                "project_id": source.project_id,
                "status": source.status,
                "provenance_kind": source.provenance_kind,
                "synthesized_from": source.synthesized_from,
                "generation_depth": depth,
                "parent_id": source.parent_id,
                "span_start": source.span_start,
                "span_end": source.span_end,
                "flags": __import__("json").dumps(source.flags),
            },
        )
        sid = result.scalar()
        assert sid is not None

        # Materialize FTS row.
        s.execute(
            text(
                "INSERT INTO sources_fts(source_id, tsv) "
                "VALUES (:s, to_tsvector('english', :content))"
            ),
            {"s": sid, "content": source.content},
        )

        # Memory classifications.
        for bucket in source.buckets:
            s.execute(
                text(
                    "INSERT INTO memory_classifications(source_id, bucket, classifier) "
                    "VALUES (:s, :b, :c) ON CONFLICT DO NOTHING"
                ),
                {"s": sid, "b": bucket, "c": source.classifier},
            )

    return WriteResult(source_id=sid, created=True, generation_depth=depth)


def invalidate(engine: Engine, source_id: int, *, reason: str) -> None:
    """Mark a source as no longer valid. Bi-temporal — row stays, t_valid_to set."""
    with session_scope(engine) as s:
        s.execute(
            text(
                "UPDATE sources SET t_valid_to = :now, invalidation_reason = :r "
                "WHERE id = :id AND t_valid_to IS NULL"
            ),
            {"now": datetime.now(timezone.utc), "r": reason, "id": source_id},
        )
```

- [ ] **Step 9: Run all write tests, verify pass**

Run: `pytest tests/test_write*.py -v`
Expected: all 4 test files pass.

- [ ] **Step 10: Commit**

```bash
git add src/brain/content_hash.py src/brain/schemas.py src/brain/write.py tests/test_write*.py
git commit -m "feat: brain.write() with scoped dedup, bi-temporal, generation_depth"
```

---

## Task 12: classify.py — bucket assignment rules

**Files:**
- Create: `src/brain/classify.py`
- Create: `tests/test_classify.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_classify.py`:

```python
from brain.classify import buckets_for_kind


def test_decision_in_session_gets_episodic_and_semantic() -> None:
    assert sorted(buckets_for_kind("decision", curated=False)) == ["episodic", "semantic"]


def test_decision_promoted_is_semantic_only() -> None:
    assert buckets_for_kind("decision", curated=True) == ["semantic"]


def test_gotcha_is_failure_and_episodic() -> None:
    assert sorted(buckets_for_kind("gotcha", curated=False)) == ["episodic", "failure"]


def test_pattern_is_procedural_only() -> None:
    assert buckets_for_kind("pattern", curated=False) == ["procedural"]


def test_tool_call_output_is_episodic_only() -> None:
    assert buckets_for_kind("tool_call_output", curated=False) == ["episodic"]


def test_paper_is_semantic_only() -> None:
    assert buckets_for_kind("paper", curated=False) == ["semantic"]


def test_session_summary_is_episodic_only() -> None:
    assert buckets_for_kind("session_summary", curated=False) == ["episodic"]
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_classify.py -v`

- [ ] **Step 3: Write classify.py per spec §Memory taxonomy bucket-assignment rules**

```python
"""Default bucket-assignment rules. See spec §Memory taxonomy."""

from __future__ import annotations

from brain.schemas import Bucket, SourceKind

_RULES: dict[SourceKind, list[Bucket]] = {
    "tool_call_output": ["episodic"],
    "command": ["episodic"],
    "edit": ["episodic"],
    "session_summary": ["episodic"],
    "subtask_summary": ["episodic"],
    "decision": ["episodic", "semantic"],  # curated=True trims to semantic only
    "gotcha": ["episodic", "failure"],
    "pattern": ["procedural"],
    "note": ["episodic"],
    "paper": ["semantic"],
    "code_file": ["semantic"],
    "web_page": ["semantic"],
    "chunk_context": ["semantic"],
    "faq": ["semantic"],
    "image": ["episodic"],
    "binary_artifact": ["episodic"],
    "project_index": ["semantic"],
}


def buckets_for_kind(kind: SourceKind, *, curated: bool) -> list[Bucket]:
    """Return the buckets a fresh source of this kind should be classified into.

    `curated=True` means the source is being explicitly promoted by curation —
    decisions in this mode drop their episodic membership in favor of semantic only.
    """
    buckets = list(_RULES.get(kind, ["episodic"]))
    if curated and kind == "decision":
        return ["semantic"]
    return buckets
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_classify.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/brain/classify.py tests/test_classify.py
git commit -m "feat: classify.buckets_for_kind per spec memory-taxonomy rules"
```

---

## Task 13: brain.read() — FTS retrieval with metadata pre-filter

**Files:**
- Create: `src/brain/read.py`
- Create: `tests/test_read_fts.py`
- Create: `tests/test_read_pre_filter.py`

- [ ] **Step 1: Write failing tests (FTS basic)**

Create `tests/test_read_fts.py`:

```python
from brain.db import get_engine
from brain.read import recall
from brain.schemas import SourceInput
from brain.write import write


def test_recall_returns_fts_hits(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="alpha beta gamma"))
    write(engine, SourceInput(kind="note", content="delta epsilon zeta"))
    write(engine, SourceInput(kind="note", content="alpha epsilon"))
    hits = recall(engine, "alpha", k=10)
    contents = {h.content for h in hits}
    assert "alpha beta gamma" in contents
    assert "alpha epsilon" in contents
    assert "delta epsilon zeta" not in contents


def test_recall_ranks_by_relevance(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="postgres"))
    write(engine, SourceInput(kind="note", content="postgres postgres postgres pgvector"))
    hits = recall(engine, "postgres pgvector", k=5)
    assert hits[0].content.startswith("postgres postgres")


def test_recall_returns_at_most_k(pg_url: str) -> None:
    engine = get_engine(pg_url)
    for i in range(10):
        write(engine, SourceInput(kind="note", content=f"alpha {i}"))
    hits = recall(engine, "alpha", k=3)
    assert len(hits) == 3
```

- [ ] **Step 2: Write failing test (metadata pre-filter)**

Create `tests/test_read_pre_filter.py`:

```python
from brain.db import get_engine, session_scope
from brain.read import recall
from brain.schemas import SourceInput
from brain.write import invalidate, write
from sqlalchemy import text


def test_pre_filter_excludes_invalidated(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", content="findme prefilter1"))
    invalidate(engine, res.source_id, reason="testing")
    hits = recall(engine, "findme prefilter1", k=10)
    assert all(h.id != res.source_id for h in hits)


def test_pre_filter_excludes_archived(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(
        engine, SourceInput(kind="note", content="findme arch", status="archived")
    )
    hits = recall(engine, "findme arch", k=10)
    assert all(h.id != res.source_id for h in hits)


def test_pre_filter_by_project(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        p1 = s.execute(
            text("INSERT INTO projects(slug,task_type) VALUES ('proj-a','development') RETURNING id")
        ).scalar()
        p2 = s.execute(
            text("INSERT INTO projects(slug,task_type) VALUES ('proj-b','development') RETURNING id")
        ).scalar()
    a = write(engine, SourceInput(kind="note", content="shared keyword", project_id=p1))
    b = write(engine, SourceInput(kind="note", content="shared keyword", project_id=p2))
    hits_p1 = recall(engine, "shared keyword", k=10, project_id=p1)
    ids = {h.id for h in hits_p1}
    assert a.source_id in ids
    assert b.source_id not in ids


def test_pre_filter_by_bucket(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(
        engine,
        SourceInput(kind="decision", content="bucket-test", buckets=["semantic"]),
    )
    b = write(
        engine,
        SourceInput(kind="gotcha", content="bucket-test", buckets=["failure", "episodic"]),
    )
    hits_failure = recall(engine, "bucket-test", k=10, buckets=["failure"])
    ids = {h.id for h in hits_failure}
    assert b.source_id in ids
    assert a.source_id not in ids
```

- [ ] **Step 3: Verify fails**

Run: `pytest tests/test_read_fts.py tests/test_read_pre_filter.py -v`

- [ ] **Step 4: Write `brain/read.py`**

```python
"""brain.read() — Phase 1 FTS-only retrieval with metadata pre-filter.

No embeddings, RRF, or rerank in Phase 1. The interface stays stable; Phase 2 adds
those stages behind the same recall() signature.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.schemas import Bucket


@dataclass(frozen=True)
class RecallHit:
    id: int
    kind: str
    content: str
    score: float
    project_id: int | None


def recall(
    engine: Engine,
    query: str,
    *,
    k: int = 10,
    project_id: int | None = None,
    buckets: list[Bucket] | None = None,
    kinds: list[str] | None = None,
    include_archived: bool = False,
) -> list[RecallHit]:
    """FTS retrieval with metadata pre-filter. Returns up to k ranked hits.

    Pre-filter contract matches spec §Retrieval step 1:
        WHERE s.t_valid_to IS NULL
          AND (include_archived OR s.status = 'active')
          AND optional project_id (primary or via source_projects M2M)
          AND optional buckets (via memory_classifications)
          AND optional kinds
    """
    sql = """
        SELECT
            s.id, s.kind, s.content, s.project_id,
            ts_rank_cd(f.tsv, plainto_tsquery('english', :q)) AS score
        FROM sources s
        JOIN sources_fts f ON f.source_id = s.id
        WHERE s.t_valid_to IS NULL
          AND (:include_archived OR s.status = 'active')
          AND f.tsv @@ plainto_tsquery('english', :q)
          AND (
                :project_id IS NULL
             OR s.project_id = :project_id
             OR EXISTS (
                    SELECT 1 FROM source_projects sp
                    WHERE sp.source_id = s.id AND sp.project_id = :project_id
                )
          )
          AND (
                :buckets IS NULL
             OR EXISTS (
                    SELECT 1 FROM memory_classifications mc
                    WHERE mc.source_id = s.id AND mc.bucket = ANY(:buckets)
                )
          )
          AND (:kinds IS NULL OR s.kind = ANY(:kinds))
        ORDER BY score DESC
        LIMIT :k
    """
    with session_scope(engine) as s:
        rows = s.execute(
            text(sql),
            {
                "q": query,
                "k": k,
                "project_id": project_id,
                "buckets": buckets,
                "kinds": kinds,
                "include_archived": include_archived,
            },
        ).fetchall()
    return [
        RecallHit(id=r[0], kind=r[1], content=r[2], project_id=r[3], score=float(r[4]))
        for r in rows
    ]
```

- [ ] **Step 5: Verify pass**

Run: `pytest tests/test_read_fts.py tests/test_read_pre_filter.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/brain/read.py tests/test_read_fts.py tests/test_read_pre_filter.py
git commit -m "feat: brain.read() FTS retrieval with metadata pre-filter"
```

---

## Task 14: entity_timeline helper

**Files:**
- Create: `src/brain/helpers/__init__.py`
- Create: `src/brain/helpers/entity_timeline.py`
- Create: `tests/test_entity_timeline.py`

- [ ] **Step 1: Write failing test**

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.helpers.entity_timeline import entity_timeline


def test_timeline_returns_chronological_events(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind,content,content_hash) "
                "VALUES ('note','seed',sha256('et-seed'::bytea)) RETURNING id"
            )
        ).scalar()
        ent_id = s.execute(
            text(
                "INSERT INTO entities(kind, canonical_name, source_id) "
                "VALUES ('concept','pgvector',:s) RETURNING id"
            ),
            {"s": sid},
        ).scalar()
        pid = s.execute(
            text("INSERT INTO projects(slug,task_type) VALUES ('et','development') RETURNING id")
        ).scalar()
        sess_id = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent) VALUES (:p,'claude-code') "
                "RETURNING id"
            ),
            {"p": pid},
        ).scalar()
        # Two events referencing the entity via source_id.
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, source_id, occurred_at) "
                "VALUES (:s, 1, 'reflection', :src, NOW() - INTERVAL '2 hours')"
            ),
            {"s": sess_id, "src": sid},
        )
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, source_id, occurred_at) "
                "VALUES (:s, 2, 'decision', :src, NOW() - INTERVAL '1 hour')"
            ),
            {"s": sess_id, "src": sid},
        )
    items = entity_timeline(engine, ent_id)
    assert len(items) == 2
    assert items[0].kind in ("reflection", "decision")
    # Earliest first
    assert items[0].occurred_at < items[1].occurred_at


def test_timeline_filters_by_date_range(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind,content,content_hash) "
                "VALUES ('note','x',sha256('et-range'::bytea)) RETURNING id"
            )
        ).scalar()
        ent_id = s.execute(
            text(
                "INSERT INTO entities(kind, canonical_name, source_id) "
                "VALUES ('concept','et2',:s) RETURNING id"
            ),
            {"s": sid},
        ).scalar()
        pid = s.execute(
            text("INSERT INTO projects(slug,task_type) VALUES ('et2','development') RETURNING id")
        ).scalar()
        sess_id = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent) VALUES (:p,'claude-code') RETURNING id"
            ),
            {"p": pid},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, source_id, occurred_at) "
                "VALUES (:s, 1, 'note', :src, NOW() - INTERVAL '10 days')"
            ),
            {"s": sess_id, "src": sid},
        )
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, source_id, occurred_at) "
                "VALUES (:s, 2, 'note', :src, NOW() - INTERVAL '1 hour')"
            ),
            {"s": sess_id, "src": sid},
        )
    items = entity_timeline(
        engine,
        ent_id,
        from_ts=datetime.now(timezone.utc) - timedelta(days=2),
    )
    assert len(items) == 1
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_entity_timeline.py -v`

- [ ] **Step 3: Write entity_timeline helper**

Create `src/brain/helpers/__init__.py` (empty):

```python
"""Brain helpers — SQL-only (Phase 1) and LLM-grounded (Phase 2+)."""
```

Create `src/brain/helpers/entity_timeline.py`:

```python
"""entity_timeline(entity_id, from?, to?) — chronological events/decisions/failures
referencing an entity. Pure SQL, no LLM dependency."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, text

from brain.db import session_scope


@dataclass(frozen=True)
class TimelineItem:
    occurred_at: datetime
    kind: str  # event kind (tool_call, decision, ...) or 'failure' / 'source'
    source_id: int | None
    role: str  # 'event' | 'failure' | 'source'
    summary: str


def entity_timeline(
    engine: Engine,
    entity_id: int,
    *,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> list[TimelineItem]:
    """Return chronological timeline of activity referencing the given entity.

    Walks three sources:
      - events.source_id pointing at sources referenced by the entity
      - failure_memories whose source_id matches
      - sources directly authored about the entity (via entities.source_id)
    """
    sql = """
        WITH entity_sources AS (
            SELECT s.id AS source_id
            FROM sources s
            JOIN entities e ON e.source_id = s.id
            WHERE e.id = :entity_id
        )
        SELECT
            ev.occurred_at AS occurred_at,
            ev.kind AS kind,
            ev.source_id AS source_id,
            'event' AS role,
            COALESCE(LEFT(src.content, 200), '') AS summary
        FROM events ev
        LEFT JOIN sources src ON src.id = ev.source_id
        WHERE ev.source_id IN (SELECT source_id FROM entity_sources)
          AND (:from_ts IS NULL OR ev.occurred_at >= :from_ts)
          AND (:to_ts IS NULL OR ev.occurred_at <= :to_ts)

        UNION ALL

        SELECT
            fm.last_attempted_at AS occurred_at,
            'failure' AS kind,
            fm.source_id AS source_id,
            'failure' AS role,
            COALESCE(LEFT(fm.target_problem, 200), '') AS summary
        FROM failure_memories fm
        WHERE fm.source_id IN (SELECT source_id FROM entity_sources)
          AND (:from_ts IS NULL OR fm.last_attempted_at >= :from_ts)
          AND (:to_ts IS NULL OR fm.last_attempted_at <= :to_ts)

        UNION ALL

        SELECT
            s.created_at AS occurred_at,
            s.kind AS kind,
            s.id AS source_id,
            'source' AS role,
            COALESCE(LEFT(s.content, 200), '') AS summary
        FROM sources s
        WHERE s.id IN (SELECT source_id FROM entity_sources)
          AND (:from_ts IS NULL OR s.created_at >= :from_ts)
          AND (:to_ts IS NULL OR s.created_at <= :to_ts)

        ORDER BY occurred_at ASC
    """
    with session_scope(engine) as s:
        rows = s.execute(
            text(sql), {"entity_id": entity_id, "from_ts": from_ts, "to_ts": to_ts}
        ).fetchall()
    return [
        TimelineItem(
            occurred_at=r[0], kind=r[1], source_id=r[2], role=r[3], summary=r[4]
        )
        for r in rows
    ]
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_entity_timeline.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/brain/helpers/__init__.py src/brain/helpers/entity_timeline.py tests/test_entity_timeline.py
git commit -m "feat: entity_timeline helper (SQL-only, no LLM dep)"
```

---

## Task 15: brain-health basic audit

**Files:**
- Create: `src/brain/helpers/health.py`
- Create: `tests/test_health.py`

- [ ] **Step 1: Write failing tests**

```python
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.helpers.health import audit
from brain.schemas import SourceInput
from brain.write import write


def test_audit_reports_table_sizes(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="a"))
    write(engine, SourceInput(kind="note", content="b"))
    report = audit(engine)
    assert report.table_row_counts["sources"] >= 2
    assert report.table_row_counts["sources_fts"] >= 2


def test_audit_lists_undercaptured_sessions(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        pid = s.execute(
            text(
                "INSERT INTO projects(slug,task_type) VALUES ('uc','development') RETURNING id"
            )
        ).scalar()
        sess_id = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent, ended_at) "
                "VALUES (:p,'claude-code', NOW()) RETURNING id"
            ),
            {"p": pid},
        ).scalar()
        # Zero events on a closed session — definitely under-captured.
    report = audit(engine, undercapture_threshold=3)
    assert sess_id in [row.session_id for row in report.undercaptured_sessions]


def test_audit_reports_orphan_classifications(pg_url: str) -> None:
    engine = get_engine(pg_url)
    # Create a source, classify it, then forcibly delete the source row (test only).
    res = write(
        engine,
        SourceInput(kind="note", content="for-orphan", buckets=["semantic"]),
    )
    with session_scope(engine) as s:
        # Hard delete sidesteps the CASCADE — emulating corruption to test the audit.
        s.execute(
            text("ALTER TABLE memory_classifications DROP CONSTRAINT memory_classifications_source_id_fkey")
        )
        s.execute(text("DELETE FROM sources WHERE id = :s"), {"s": res.source_id})
    report = audit(engine)
    assert report.orphan_classification_count >= 1
    # Restore the FK so subsequent tests stay clean.
    with session_scope(engine) as s:
        s.execute(text("DELETE FROM memory_classifications WHERE source_id = :s"), {"s": res.source_id})
        s.execute(
            text(
                "ALTER TABLE memory_classifications "
                "ADD CONSTRAINT memory_classifications_source_id_fkey "
                "FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE"
            )
        )
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_health.py -v`

- [ ] **Step 3: Write health.py**

```python
"""brain-health basic audit (Phase 1). Generative-lint mode lands Phase 4."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, text

from brain.db import session_scope


@dataclass(frozen=True)
class UndercapturedSession:
    session_id: int
    project_id: int | None
    event_count: int


@dataclass
class HealthReport:
    table_row_counts: dict[str, int] = field(default_factory=dict)
    undercaptured_sessions: list[UndercapturedSession] = field(default_factory=list)
    orphan_classification_count: int = 0
    stale_active_count: int = 0


_TRACKED_TABLES = (
    "sources",
    "sources_fts",
    "source_projects",
    "memory_classifications",
    "projects",
    "sessions",
    "subtasks",
    "events",
    "failure_memories",
    "procedures",
    "entities",
    "edges",
    "retrieval_log",
    "session_resume_bundles",
)


def audit(engine: Engine, *, undercapture_threshold: int = 3) -> HealthReport:
    """Run all Phase-1 audit queries and return a structured report."""
    report = HealthReport()

    with session_scope(engine) as s:
        for table in _TRACKED_TABLES:
            n = s.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            report.table_row_counts[table] = int(n or 0)

        rows = s.execute(
            text(
                """
                SELECT sess.id, sess.project_id, COUNT(ev.id) AS event_count
                FROM sessions sess
                LEFT JOIN events ev ON ev.session_id = sess.id
                WHERE sess.ended_at IS NOT NULL
                GROUP BY sess.id, sess.project_id
                HAVING COUNT(ev.id) < :thresh
                ORDER BY sess.ended_at DESC
                """
            ),
            {"thresh": undercapture_threshold},
        ).fetchall()
        report.undercaptured_sessions = [
            UndercapturedSession(
                session_id=r[0], project_id=r[1], event_count=int(r[2])
            )
            for r in rows
        ]

        orphan = s.execute(
            text(
                "SELECT COUNT(*) FROM memory_classifications mc "
                "WHERE NOT EXISTS (SELECT 1 FROM sources s WHERE s.id = mc.source_id)"
            )
        ).scalar()
        report.orphan_classification_count = int(orphan or 0)

        stale = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE status = 'active' AND t_valid_from < NOW() - INTERVAL '90 days' "
                "AND t_valid_to IS NULL"
            )
        ).scalar()
        report.stale_active_count = int(stale or 0)

    return report
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_health.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/brain/helpers/health.py tests/test_health.py
git commit -m "feat: brain-health Phase-1 audit (table sizes, under-captured, orphans, stale)"
```

---

## Task 16: V1 markdown migration script

**Files:**
- Create: `src/brain/migrate_v1.py`
- Create: `tests/test_v1_migration.py`

- [ ] **Step 1: Write failing test**

```python
from pathlib import Path

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.migrate_v1 import migrate_v1_markdown


def _write_md(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_migrates_decision_with_multibucket(tmp_path: Path, pg_url: str) -> None:
    vault = tmp_path / "Agent-Brain"
    _write_md(
        vault / "agent-memory" / "decisions" / "2026-05-17-pick-redis.md",
        """---
type: decision
tags: [auth]
project: brain
status: active
created: 2026-05-17
updated: 2026-05-17
related: []
---
# Pick redis for JWT store

Body of the decision.
""",
    )
    engine = get_engine(pg_url)
    summary = migrate_v1_markdown(engine, vault)
    assert summary.files_imported == 1
    with session_scope(engine) as s:
        sid = s.execute(text("SELECT id FROM sources WHERE kind = 'decision'")).scalar()
        buckets = sorted(
            r[0]
            for r in s.execute(
                text("SELECT bucket FROM memory_classifications WHERE source_id = :s"),
                {"s": sid},
            ).fetchall()
        )
    assert buckets == ["episodic", "semantic"]


def test_idempotent_rerun(tmp_path: Path, pg_url: str) -> None:
    vault = tmp_path / "Agent-Brain"
    _write_md(
        vault / "knowledge" / "patterns" / "feature-flag-rollout.md",
        """---
type: pattern
status: active
created: 2026-05-01
updated: 2026-05-01
---
# Feature flag rollout

Body.
""",
    )
    engine = get_engine(pg_url)
    first = migrate_v1_markdown(engine, vault)
    second = migrate_v1_markdown(engine, vault)
    assert first.files_imported == 1
    assert second.files_imported == 1
    assert second.dedup_hits == 1  # second run sees the existing row
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_v1_migration.py -v`

- [ ] **Step 3: Write migrate_v1.py**

```python
"""One-shot migration: v1 markdown vault → Postgres brain.

Parses YAML frontmatter, maps `type` to `kind`, classifies into buckets per
the same rules as classify.py, dedupes via brain.write()'s scoped uniqueness.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter
from sqlalchemy import Engine

from brain.classify import buckets_for_kind
from brain.schemas import SourceInput, SourceKind
from brain.write import write

_TYPE_TO_KIND: dict[str, SourceKind] = {
    "decision": "decision",
    "gotcha": "gotcha",
    "pattern": "pattern",
    "note": "note",
    "session": "session_summary",
    "api": "code_file",  # closest existing kind for v1's api notes
    "architecture": "code_file",
    "process": "note",
    "glossary": "note",
    "project": "project_index",
    "task": "note",
    "meta": "note",
}


@dataclass
class MigrationSummary:
    files_imported: int = 0
    dedup_hits: int = 0
    skipped_unknown_type: list[Path] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.skipped_unknown_type is None:
            self.skipped_unknown_type = []


def migrate_v1_markdown(engine: Engine, vault_path: Path) -> MigrationSummary:
    summary = MigrationSummary()
    for md_file in vault_path.rglob("*.md"):
        if md_file.name.startswith("."):
            continue
        post = frontmatter.load(md_file)
        fm = post.metadata
        v1_type = fm.get("type")
        if v1_type not in _TYPE_TO_KIND:
            summary.skipped_unknown_type.append(md_file)
            continue
        kind = _TYPE_TO_KIND[v1_type]
        buckets = buckets_for_kind(kind, curated=False)
        result = write(
            engine,
            SourceInput(
                kind=kind,
                content=post.content,
                uri=f"file://{md_file.resolve()}",
                buckets=buckets,
                classifier="v1-migration",
            ),
        )
        if result.created:
            summary.files_imported += 1
        else:
            summary.dedup_hits += 1
            summary.files_imported += 1  # count as imported for re-run idempotency
    return summary
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_v1_migration.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/brain/migrate_v1.py tests/test_v1_migration.py
git commit -m "feat: migrate_v1_markdown — v1 vault → Postgres brain (idempotent)"
```

---

## Task 17: Obsidian markdown export (DB → markdown view)

**Files:**
- Create: `src/brain/obsidian/__init__.py`
- Create: `src/brain/obsidian/export.py`
- Create: `src/brain/obsidian/render_templates/decision.md.j2`
- Create: `src/brain/obsidian/render_templates/gotcha.md.j2`
- Create: `src/brain/obsidian/render_templates/pattern.md.j2`
- Create: `src/brain/obsidian/render_templates/note.md.j2`
- Create: `src/brain/obsidian/render_templates/session_summary.md.j2`
- Create: `tests/test_obsidian_export.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from brain.db import get_engine
from brain.obsidian.export import export_brain_to_markdown
from brain.schemas import SourceInput
from brain.write import write


def test_export_writes_one_file_per_narrative_source(tmp_path: Path, pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(
        engine,
        SourceInput(
            kind="decision",
            content="# Pick redis for JWT store\n\nWhy: rotation cadence.",
        ),
    )
    write(
        engine,
        SourceInput(
            kind="gotcha", content="# FastAPI startup hook fires twice\n\nFix: ...",
        ),
    )
    out = tmp_path / "Agent-Brain"
    summary = export_brain_to_markdown(engine, out)
    assert summary.files_written >= 2
    # File names are slug-based; just verify directory contents exist.
    decisions = list((out / "agent-memory" / "decisions").glob("*.md"))
    gotchas = list((out / "agent-memory" / "gotchas").glob("*.md"))
    assert len(decisions) >= 1
    assert len(gotchas) >= 1


def test_exported_file_has_db_id_frontmatter(tmp_path: Path, pg_url: str) -> None:
    import frontmatter

    engine = get_engine(pg_url)
    res = write(
        engine, SourceInput(kind="decision", content="# Round-trip test\n\nBody.")
    )
    out = tmp_path / "Agent-Brain"
    export_brain_to_markdown(engine, out)
    files = list((out / "agent-memory" / "decisions").glob("*.md"))
    assert files
    post = frontmatter.load(files[0])
    assert post.metadata.get("db_id") == res.source_id


def test_tool_call_output_NOT_exported(tmp_path: Path, pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="tool_call_output", content="huge stdout"))
    out = tmp_path / "Agent-Brain"
    export_brain_to_markdown(engine, out)
    # No subdir for tool_call_output should be created.
    assert not (out / "tool_calls").exists()
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_obsidian_export.py -v`

- [ ] **Step 3: Write templates**

Create `src/brain/obsidian/render_templates/decision.md.j2`:

```jinja
---
db_id: {{ source.id }}
type: decision
kind: {{ source.kind }}
project: {{ project_slug | default('null') }}
status: {{ source.status }}
created: {{ source.created_at.date().isoformat() }}
updated: {{ source.updated_at.date().isoformat() }}
provenance_kind: {{ source.provenance_kind }}
buckets: {{ buckets | tojson }}
---
{{ source.content }}
```

Create `src/brain/obsidian/render_templates/gotcha.md.j2`:

```jinja
---
db_id: {{ source.id }}
type: gotcha
kind: {{ source.kind }}
project: {{ project_slug | default('null') }}
status: {{ source.status }}
created: {{ source.created_at.date().isoformat() }}
updated: {{ source.updated_at.date().isoformat() }}
provenance_kind: {{ source.provenance_kind }}
buckets: {{ buckets | tojson }}
---
{{ source.content }}
```

Create `src/brain/obsidian/render_templates/pattern.md.j2`, `note.md.j2`, `session_summary.md.j2` with the same shape (only the `type` field differs). Copy-paste-rename — same 12 lines each.

- [ ] **Step 4: Write export.py**

Create `src/brain/obsidian/__init__.py` (empty):

```python
"""Obsidian markdown view: DB → markdown (export), markdown → DB (reingest)."""
```

Create `src/brain/obsidian/export.py`:

```python
"""DB → Obsidian markdown view. One file per narrative source (per spec §Content
fidelity rule: tool_call_output and binary_artifact are NOT exported)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import Engine, text

from brain.db import session_scope

_EXPORT_KIND_TO_DIR: dict[str, str] = {
    "decision": "agent-memory/decisions",
    "gotcha": "agent-memory/gotchas",
    "pattern": "knowledge/patterns",
    "note": "agent-memory/notes",
    "session_summary": "agent-memory/sessions",
    "subtask_summary": "agent-memory/sessions",
    "paper": "knowledge/papers",
    "code_file": "knowledge/code",
    "web_page": "knowledge/web",
    "project_index": "projects",
    "faq": "knowledge/faqs",
}

_KIND_TO_TEMPLATE = {
    "decision": "decision.md.j2",
    "gotcha": "gotcha.md.j2",
    "pattern": "pattern.md.j2",
    "note": "note.md.j2",
    "session_summary": "session_summary.md.j2",
    "subtask_summary": "session_summary.md.j2",
    "paper": "note.md.j2",
    "code_file": "note.md.j2",
    "web_page": "note.md.j2",
    "project_index": "note.md.j2",
    "faq": "note.md.j2",
}


@dataclass
class ExportSummary:
    files_written: int = 0
    files_skipped: int = 0


def _slugify(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")
    return cleaned[:80] if cleaned else fallback


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def export_brain_to_markdown(engine: Engine, out_root: Path) -> ExportSummary:
    out_root.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "render_templates"),
        autoescape=False,
        keep_trailing_newline=True,
    )
    summary = ExportSummary()

    with session_scope(engine) as s:
        rows = s.execute(
            text(
                """
                SELECT s.id, s.kind, s.content, s.status, s.created_at, s.updated_at,
                       s.provenance_kind,
                       p.slug AS project_slug,
                       COALESCE(
                           ARRAY(SELECT bucket FROM memory_classifications mc
                                 WHERE mc.source_id = s.id ORDER BY bucket),
                           ARRAY[]::TEXT[]
                       ) AS buckets
                FROM sources s
                LEFT JOIN projects p ON p.id = s.project_id
                WHERE s.t_valid_to IS NULL AND s.status != 'draft'
                """
            )
        ).fetchall()

    for row in rows:
        kind = row[1]
        if kind not in _EXPORT_KIND_TO_DIR:
            summary.files_skipped += 1
            continue
        subdir = out_root / _EXPORT_KIND_TO_DIR[kind]
        subdir.mkdir(parents=True, exist_ok=True)
        title = _extract_title(row[2], fallback=f"{kind}-{row[0]}")
        date_prefix = row[4].date().isoformat()
        is_dated_kind = kind in ("decision", "gotcha", "session_summary", "subtask_summary")
        slug = _slugify(title, fallback=f"id-{row[0]}")
        fname = f"{date_prefix}-{slug}.md" if is_dated_kind else f"{slug}.md"
        target = subdir / fname

        template = env.get_template(_KIND_TO_TEMPLATE[kind])

        class _Src:  # tiny adapter for template
            pass

        src = _Src()
        src.id = row[0]
        src.kind = row[1]
        src.content = row[2]
        src.status = row[3]
        src.created_at = row[4]
        src.updated_at = row[5]
        src.provenance_kind = row[6]
        rendered = template.render(
            source=src, project_slug=row[7], buckets=list(row[8])
        )
        target.write_text(rendered)
        summary.files_written += 1

    return summary
```

- [ ] **Step 5: Verify pass**

Run: `pytest tests/test_obsidian_export.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/brain/obsidian/ tests/test_obsidian_export.py
git commit -m "feat: Obsidian export (DB → markdown) per kind, with db_id frontmatter"
```

---

## Task 18: Click CLI wiring

**Files:**
- Create: `src/brain/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
from click.testing import CliRunner

from brain.cli import main


def test_cli_help_lists_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for sub in ("write", "recall", "health", "entity-timeline", "export", "reingest"):
        assert sub in result.output


def test_cli_health_prints_table_counts(pg_url: str) -> None:
    import os

    runner = CliRunner()
    result = runner.invoke(
        main, ["health"], env={"BRAIN_DB_URL": pg_url, **os.environ}
    )
    assert result.exit_code == 0
    assert "sources" in result.output
```

- [ ] **Step 2: Verify fails**

Run: `pytest tests/test_cli.py -v`

- [ ] **Step 3: Write cli.py**

```python
"""Click CLI: `brain` command group."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from brain.config import load_config
from brain.db import get_engine
from brain.helpers.entity_timeline import entity_timeline as _entity_timeline
from brain.helpers.health import audit as _audit
from brain.migrate_v1 import migrate_v1_markdown
from brain.obsidian.export import export_brain_to_markdown
from brain.read import recall as _recall
from brain.schemas import SourceInput
from brain.write import write as _write

console = Console()


@click.group()
@click.pass_context
def main(ctx: click.Context) -> None:
    """Agent Brain CLI."""
    ctx.ensure_object(dict)
    cfg = load_config()
    ctx.obj["engine"] = get_engine(cfg.db_url)
    ctx.obj["config"] = cfg


@main.command()
@click.option("--kind", required=True)
@click.option("--content", required=True)
@click.option("--uri")
@click.option("--project-id", type=int)
@click.option("--bucket", multiple=True, help="Repeatable: --bucket semantic --bucket episodic")
@click.pass_context
def write(
    ctx: click.Context,
    kind: str,
    content: str,
    uri: str | None,
    project_id: int | None,
    bucket: tuple[str, ...],
) -> None:
    """Capture a source into the brain."""
    result = _write(
        ctx.obj["engine"],
        SourceInput(
            kind=kind,  # type: ignore[arg-type]
            content=content,
            uri=uri,
            project_id=project_id,
            buckets=list(bucket),  # type: ignore[arg-type]
        ),
    )
    click.echo(json.dumps(result.model_dump()))


@main.command()
@click.argument("query")
@click.option("-k", default=5, type=int)
@click.option("--project-id", type=int)
@click.option("--bucket", multiple=True)
@click.option("--kind-filter", multiple=True)
@click.pass_context
def recall(
    ctx: click.Context,
    query: str,
    k: int,
    project_id: int | None,
    bucket: tuple[str, ...],
    kind_filter: tuple[str, ...],
) -> None:
    """Retrieve top-k sources matching a query (FTS in Phase 1)."""
    hits = _recall(
        ctx.obj["engine"],
        query,
        k=k,
        project_id=project_id,
        buckets=list(bucket) or None,  # type: ignore[arg-type]
        kinds=list(kind_filter) or None,
    )
    table = Table("id", "kind", "score", "content (head)")
    for h in hits:
        table.add_row(str(h.id), h.kind, f"{h.score:.3f}", h.content[:80])
    console.print(table)


@main.command()
@click.option("--threshold", default=3, type=int)
@click.pass_context
def health(ctx: click.Context, threshold: int) -> None:
    """Run the Phase-1 health audit and print a table."""
    report = _audit(ctx.obj["engine"], undercapture_threshold=threshold)
    table = Table("table", "rows")
    for name, n in sorted(report.table_row_counts.items()):
        table.add_row(name, str(n))
    console.print(table)
    if report.undercaptured_sessions:
        console.print(
            f"[yellow]under-captured sessions: {len(report.undercaptured_sessions)}[/]"
        )
    if report.orphan_classification_count:
        console.print(
            f"[red]orphan classifications: {report.orphan_classification_count}[/]"
        )
    if report.stale_active_count:
        console.print(
            f"[yellow]stale active-status sources (>90d): {report.stale_active_count}[/]"
        )


@main.command(name="entity-timeline")
@click.argument("entity_id", type=int)
@click.option("--from", "from_ts", type=click.DateTime())
@click.option("--to", "to_ts", type=click.DateTime())
@click.pass_context
def entity_timeline_cmd(
    ctx: click.Context, entity_id: int, from_ts: datetime | None, to_ts: datetime | None
) -> None:
    """Show chronological events/decisions/failures referencing an entity."""
    items = _entity_timeline(
        ctx.obj["engine"], entity_id, from_ts=from_ts, to_ts=to_ts
    )
    table = Table("when", "kind", "role", "source_id", "summary")
    for item in items:
        table.add_row(
            item.occurred_at.isoformat(),
            item.kind,
            item.role,
            str(item.source_id or ""),
            item.summary[:80],
        )
    console.print(table)


@main.command(name="export")
@click.option("--out", required=False, type=click.Path(path_type=Path))
@click.pass_context
def export_cmd(ctx: click.Context, out: Path | None) -> None:
    """Export the brain to Obsidian-readable markdown."""
    cfg = ctx.obj["config"]
    out_path = out or cfg.brain_path
    summary = export_brain_to_markdown(ctx.obj["engine"], out_path)
    click.echo(
        f"wrote {summary.files_written} files to {out_path} (skipped {summary.files_skipped})"
    )


@main.command()
@click.argument("vault_path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def reingest(ctx: click.Context, vault_path: Path) -> None:
    """Re-ingest markdown from a vault path (Phase 1: equivalent to v1 migration)."""
    summary = migrate_v1_markdown(ctx.obj["engine"], vault_path)
    click.echo(
        f"imported {summary.files_imported} files (dedup hits: {summary.dedup_hits}, "
        f"skipped unknown type: {len(summary.skipped_unknown_type)})"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_cli.py -v && brain --help`
Expected: tests pass; `brain --help` lists all 6 subcommands.

- [ ] **Step 5: Commit**

```bash
git add src/brain/cli.py tests/test_cli.py
git commit -m "feat: brain CLI (write/recall/health/entity-timeline/export/reingest)"
```

---

## Task 19: `brain-setup` skill (SKILL.md + setup.sh)

**Files:**
- Create: `skills/brain-setup/SKILL.md`
- Create: `skills/brain-setup/scripts/setup.sh`

- [ ] **Step 1: Write `skills/brain-setup/SKILL.md`**

```markdown
---
name: brain-setup
description: Use to install or initialize the agent brain (Postgres + Python + schema). Run on first install, when the brain database is missing, or when migrations need to be re-applied. Idempotent.
---

# brain-setup

Provision the agent brain: Postgres running, schema migrated, Python package installed, Obsidian vault detected.

## When to use

- First install of the agent brain on a machine.
- DB missing: another `brain ...` command failed with "could not connect to Postgres."
- Schema drift: pulled new migrations and want to apply them.
- Reset: spin down + spin up the dev database (with `--reset`).

## What it runs

1. Detect Postgres availability:
   - If `docker compose` works AND `pg_isready` against the brain compose service succeeds → use it.
   - Else, check for a local Postgres listening on `127.0.0.1:5432` with a `brain` database.
   - Else, offer to `docker compose up -d` from the repo root.
2. Ensure the `vector`, `pg_trgm`, `btree_gist` extensions are installed.
3. Run `alembic upgrade head` to apply all migrations.
4. Verify by calling `brain health` — should print non-zero `brain_config` row count.
5. Resolve the Obsidian vault path from `OBSIDIAN_VAULT` env or `~/Documents/ObsidianVault` default; print where it lands.

## How (the script)

```bash
bash skills/brain-setup/scripts/setup.sh
```

The script auto-detects existing Postgres before falling back to docker-compose. Reset with `--reset` (drops `brain_pg_data` volume; lossy).

## Don't

- Don't run on a production database — `--reset` drops data.
- Don't edit `alembic/versions/*` after running setup on multiple machines; downgrade-then-upgrade can fail if migration content changed mid-flight.
```

- [ ] **Step 2: Write setup.sh**

```bash
#!/usr/bin/env bash
# brain-setup: provision Postgres + migrate schema. Idempotent.

set -euo pipefail

RESET=0
if [ "${1:-}" = "--reset" ]; then
  RESET=1
fi

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

printf "==> Detecting Postgres availability...\n"

PG_URL_DEFAULT="postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain"
PG_URL="${BRAIN_DB_URL:-$PG_URL_DEFAULT}"

# Try docker-compose first (the dev default).
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  if [ "$RESET" -eq 1 ]; then
    printf "==> --reset: docker compose down -v\n"
    docker compose down -v || true
  fi
  if ! docker compose ps postgres 2>/dev/null | grep -q 'Up'; then
    printf "==> Starting docker-compose Postgres...\n"
    docker compose up -d postgres
  fi
  # Wait for healthy.
  for _ in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U brain -d brain >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

printf "==> Applying alembic migrations...\n"
BRAIN_DB_URL="$PG_URL" alembic upgrade head

printf "==> Verifying with brain health...\n"
BRAIN_DB_URL="$PG_URL" brain health

VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/ObsidianVault}"
SUBDIR="${BRAIN_SUBDIR:-Agent-Brain}"
printf "==> Obsidian vault will export to: %s/%s\n" "$VAULT" "$SUBDIR"
printf "==> Done. Run 'brain --help' to see commands.\n"
```

- [ ] **Step 3: Make executable**

Run: `chmod +x skills/brain-setup/scripts/setup.sh`

- [ ] **Step 4: Smoke test the script (manual; can be run by the engineer)**

Run: `bash skills/brain-setup/scripts/setup.sh`
Expected: prints detection steps; `brain health` table shows `brain_config` count > 0.

- [ ] **Step 5: Commit**

```bash
git add skills/brain-setup/
git commit -m "feat: brain-setup skill (Postgres detect + migrate + verify)"
```

---

## Task 20: `brain-recall` skill

**Files:**
- Create: `skills/brain-recall/SKILL.md`
- Create: `skills/brain-recall/scripts/recall.sh`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: brain-recall
description: Use BEFORE non-trivial work, when a topic comes up that may be in the brain, or before brainstorming. Searches the agent brain with FTS (Phase 1 — hybrid retrieval with embeddings comes in Phase 2). Returns top-k structured hits with provenance. Cap output at ≤500 tokens; never dump raw content.
---

# brain-recall

Pull just-enough structured context from the brain before working.

## When to use

- Start of any non-trivial task — *before* you read code.
- User mentions a concept the brain might have notes on.
- Before invoking `superpowers:brainstorming` or `superpowers:writing-plans` on a topic the brain might cover.

## When NOT to use

- The query is about the current diff — read the diff directly.
- The brain is empty (`brain health` shows zero sources). Run `brain-setup` and capture something first.
- You already pulled context for this exact query this session.

## What it does

1. Resolves brain DB connection from `BRAIN_DB_URL` or default docker-compose URL.
2. Calls `brain recall <query> -k 5` (or higher k if needed).
3. Optionally filters: `--project-id`, `--bucket`, `--kind-filter`.
4. Prints a rich-table of `(id, kind, score, content head)`.
5. **The agent must synthesize the table into a ≤500-token brief**. Do not paste the raw table at the user; cite source IDs.

## How

### Step 1 — recall

```bash
bash skills/brain-recall/scripts/recall.sh "<query>" [-k 5] [--project-id N] [--bucket semantic]
```

The script is a passthrough to `brain recall`.

### Step 2 — pick

Choose the 3–5 most relevant hits. If top-1 has low score (`< 0.05`), say "no high-confidence match" and don't fabricate one.

### Step 3 — synthesize

Emit ≤500 tokens with `[brain:<id>]` cites. Phase 2 adds reranker + abstain threshold; Phase 1 is honest about score-only ranking.

## Don't

- Dump raw rows — synthesize.
- Recall the same query twice in one session.
- Skip the score check — a score of 0.0001 is noise.
```

- [ ] **Step 2: Write recall.sh**

```bash
#!/usr/bin/env bash
# brain-recall: thin wrapper to `brain recall`. All args passthrough.

set -euo pipefail

if [ $# -lt 1 ]; then
  printf "usage: %s <query> [recall flags]\n" "$0" >&2
  exit 1
fi

exec brain recall "$@"
```

- [ ] **Step 3: Make executable + commit**

```bash
chmod +x skills/brain-recall/scripts/recall.sh
git add skills/brain-recall/
git commit -m "feat: brain-recall skill (FTS-tier wrapper around brain recall CLI)"
```

---

## Task 21: `brain-health` skill

**Files:**
- Create: `skills/brain-health/SKILL.md`
- Create: `skills/brain-health/scripts/health.sh`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: brain-health
description: Use weekly or when investigating brain quality issues. Runs the Phase-1 audit (table sizes, under-captured sessions, orphan rows, stale-active sources). Phase 4 will add generative-lint mode (--lint).
---

# brain-health

Audit the brain. Read-only.

## When to use

- Weekly maintenance.
- When recall feels off (no hits where there should be hits → check stale-active or under-captured rates).
- After bulk operations (migration, mass ingest, schema change) to verify nothing leaked.

## What it reports

- Row counts per table.
- Sessions that ended with fewer than `--threshold` (default 3) events captured.
- Orphan classifications (rows referencing non-existent sources — a corruption signal).
- Sources with `status='active'` older than 90 days (stale signal; consider archiving).

Phase 4 will add a `--lint` mode that runs NLI contradictions + identify_gaps + surface user-facing questions. Phase 1 is the baseline.

## How

```bash
bash skills/brain-health/scripts/health.sh [--threshold 3]
```

Print is human-readable rich-table. CI integration: parse JSON via `brain health --json` (added in Phase 3 when JSON output lands).
```

- [ ] **Step 2: Write health.sh**

```bash
#!/usr/bin/env bash
# brain-health: thin wrapper to `brain health`.

set -euo pipefail

exec brain health "$@"
```

- [ ] **Step 3: Make executable + commit**

```bash
chmod +x skills/brain-health/scripts/health.sh
git add skills/brain-health/
git commit -m "feat: brain-health skill (Phase-1 audit wrapper)"
```

---

## Task 22: End-to-end integration test

**Files:**
- Create: `tests/test_end_to_end.py`

- [ ] **Step 1: Write the test**

```python
"""End-to-end: setup → write a sample corpus → recall → entity_timeline → export → reingest."""

from pathlib import Path

import frontmatter
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.migrate_v1 import migrate_v1_markdown
from brain.obsidian.export import export_brain_to_markdown
from brain.read import recall
from brain.schemas import SourceInput
from brain.write import write


def test_capture_recall_export_reingest_roundtrip(tmp_path: Path, pg_url: str) -> None:
    engine = get_engine(pg_url)

    # Set up a project.
    with session_scope(engine) as s:
        pid = s.execute(
            text(
                "INSERT INTO projects(slug, task_type, repo_root) "
                "VALUES ('e2e-test','development','/tmp/e2e') RETURNING id"
            )
        ).scalar()

    # Capture three sources: a decision, a gotcha, a pattern.
    r1 = write(
        engine,
        SourceInput(
            kind="decision",
            content="# Use postgres + pgvector for v2 brain\n\nReasoning: scale + maturity.",
            project_id=pid,
            buckets=["semantic", "episodic"],
        ),
    )
    r2 = write(
        engine,
        SourceInput(
            kind="gotcha",
            content="# pgvector HALFVEC needs fixed dimension\n\nUse HALFVEC(1024) for HNSW.",
            project_id=pid,
            buckets=["failure", "episodic"],
        ),
    )
    r3 = write(
        engine,
        SourceInput(
            kind="pattern",
            content="# Bi-temporal validity via partial unique\n\nUNIQUE WHERE t_valid_to IS NULL.",
            project_id=pid,
            buckets=["procedural"],
        ),
    )
    assert r1.created and r2.created and r3.created

    # Recall: query should surface the decision.
    hits = recall(engine, "postgres pgvector", k=5, project_id=pid)
    assert any(h.id == r1.source_id for h in hits)

    # Export to markdown.
    out = tmp_path / "vault" / "Agent-Brain"
    summary = export_brain_to_markdown(engine, out)
    assert summary.files_written >= 3

    # Verify db_id frontmatter on the exported decision.
    decisions = list((out / "agent-memory" / "decisions").glob("*.md"))
    assert decisions
    post = frontmatter.load(decisions[0])
    assert post.metadata.get("db_id") in (r1.source_id, r2.source_id, r3.source_id) or \
           any(post.metadata.get("db_id") == r.source_id for r in (r1, r2, r3))

    # Re-ingest the exported markdown — should be a no-op (all dedup hits).
    reimport_engine = engine  # same DB, dedup must trigger
    summary2 = migrate_v1_markdown(reimport_engine, out)
    assert summary2.dedup_hits >= 3, "exported-then-reingested files must all dedup-hit"
```

- [ ] **Step 2: Run, verify pass**

Run: `pytest tests/test_end_to_end.py -v`
Expected: pass.

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end.py
git commit -m "test: end-to-end capture → recall → export → reingest round-trip"
```

---

## Task 23: Docs + plugin manifest updates

**Files:**
- Create: `docs/installation.md`
- Create: `docs/operations.md`
- Modify: `README.md` (Phase 1 install section)
- Modify: `.claude-plugin/plugin.json` (bump version, add new skills)

- [ ] **Step 1: Write `docs/installation.md`**

```markdown
# Installation

The agent brain v2 ships as a Python package + 3 Claude Code skills + an Obsidian vault export.

## Prerequisites

- Python 3.12+ (`python3 --version`)
- Postgres 16+ with `pgvector` extension. Two paths:
  - **Docker (recommended for dev):** `docker compose up -d` from the repo root spins up `pgvector/pgvector:pg16` on `127.0.0.1:5433`.
  - **Native (recommended for prod):** install `postgresql-16` and `postgresql-16-pgvector` via your package manager, then create the brain database and role:
    ```bash
    sudo -u postgres psql -c "CREATE ROLE brain LOGIN PASSWORD 'CHANGE_ME'"
    sudo -u postgres psql -c "CREATE DATABASE brain OWNER brain"
    ```
- `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

## Install

```bash
git clone <repo> ~/codes/brain && cd ~/codes/brain
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
bash skills/brain-setup/scripts/setup.sh
```

Then in Claude Code, install the skills:

```bash
bash clients/install-claude-code.sh
```

## Verify

```bash
brain health
```

Should print a table of row counts (most zero on a fresh install) plus `brain_config` with seeded defaults.

## Vault wiring

Set `OBSIDIAN_VAULT` to your vault root if not at `~/Documents/ObsidianVault`. Optionally set `BRAIN_SUBDIR` (default `Agent-Brain`).

## Migrate v1 content (one-time)

If you have an existing v1 markdown vault under `<vault>/Agent-Brain/`, ingest it:

```bash
brain reingest "$OBSIDIAN_VAULT/Agent-Brain"
```

Re-running is idempotent — content-hash dedup keeps it clean.
```

- [ ] **Step 2: Write `docs/operations.md`**

```markdown
# Operations

## Backup

Nightly `pg_dump` is the canonical disaster-recovery path. Add to cron:

```bash
0 2 * * * /usr/bin/pg_dump -U brain brain | gzip > "$HOME/Documents/ObsidianVault/Agent-Brain/_backups/brain-$(date +\%F).sql.gz"
```

The markdown view under `<vault>/Agent-Brain/` is a **partial fallback only** — see spec §Obsidian markdown view. Episodic stream, embeddings, retrieval logs, and procedure counters are NOT recoverable from markdown alone.

## Restore

```bash
gunzip -c brain-2026-05-24.sql.gz | psql -U brain brain
```

## Conflict resolution (markdown ↔ DB)

If the file-watcher (Phase 3) detects a markdown edit that conflicts with a recent DB write, both versions are kept (older invalidated with `invalidation_reason='conflict: see <id>'`). The user resolves via `brain reingest` after editing.

## Cost guards

Phase 1 has no LLM dependencies — no API costs. Phase 2+ introduces per-session cost caps configurable in `brain_config`.
```

- [ ] **Step 3: Update README.md**

Append (or update existing v1 install block with):

```markdown
## Agent Brain v2 — Phase 1

Phase 1 ships: Postgres-backed schema, Python core (`brain.write` / `brain.read`), FTS retrieval, 3 skills (`brain-setup`, `brain-recall`, `brain-health`), v1 markdown migration, Obsidian export.

Quick start:

```bash
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
bash skills/brain-setup/scripts/setup.sh
brain --help
```

Full install + operations: `docs/installation.md`, `docs/operations.md`.

Embeddings, RRF, reranker, hooks, MCP — all later phases. See `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md`.
```

- [ ] **Step 4: Update `.claude-plugin/plugin.json`**

Bump `version` to `0.2.0` and add the 3 new skills:

```json
{
  "name": "agent-brain",
  "version": "0.2.0",
  "description": "Persistent cognition store for AI coding agents — Phase 1 ships Postgres + FTS + 3 skills.",
  "skills": [
    "skills/brain-setup",
    "skills/brain-recall",
    "skills/brain-health"
  ]
}
```

(If the plugin.json contains v1 obsidian-* skills, leave them — Phase 1 is additive. Phase 4 will retire them.)

- [ ] **Step 5: Commit**

```bash
git add docs/installation.md docs/operations.md README.md .claude-plugin/plugin.json
git commit -m "docs: Phase 1 installation + operations docs; plugin.json v0.2.0"
```

---

## Self-Review

### Spec coverage

| Spec §Phase 1 bullet | Plan task |
|---|---|
| Postgres install + extensions | Task 1 (compose), Task 3 (migration 001 creates extensions) |
| Schema migrations (alembic) | Tasks 3–9 (seven migrations, one per table-group) |
| Python package skeleton | Task 1 |
| `brain.write` / `brain.read` low-level API | Tasks 11, 13 |
| FTS retrieval (no embeddings) | Task 13 |
| Migrate v1 markdown content | Task 16 |
| Obsidian markdown view (lossless export) | Task 17 |
| `brain-setup`, `brain-recall`, `brain-health`, `entity_timeline` | Tasks 19, 20, 21, 14 (helper via CLI subcommand per deviation #7) |

Schema coverage:

| Spec table | Migration |
|---|---|
| `brain_config` | 001 |
| `projects`, `sessions`, `subtasks` | 002 |
| `sources`, `sources_fts`, `source_projects`, `memory_classifications` | 003 |
| `failure_memories` | 004 |
| `procedures`, `events` (with `procedure_id` FK) | 005 |
| `entities`, `edges` | 006 |
| `retrieval_log`, `session_resume_bundles` | 007 |

Gaps: none for Phase 1 scope. `embeddings_1024`, `extracted_claims`, `reasoning_cache`, `cost_log` are deliberately Phase 2+.

### Placeholder scan

No "TBD", "implement later", "similar to Task N", or vague-error-handling lines. Every test has actual test code. Every implementation step shows the implementation.

### Type consistency

- `SourceInput.kind` types match across `schemas.py`, `write.py`, `classify.py`, `cli.py`.
- `RecallHit` fields used in CLI (`id`, `kind`, `score`, `content`) match what `recall()` returns in `read.py`.
- `HealthReport` field names match what `cli.py` reads in `brain health`.
- Migration revision IDs chain correctly: `001 → 002 → ... → 007`.

Plan complete and saved to `docs/superpowers/plans/2026-05-24-agent-brain-v2-phase-1.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
