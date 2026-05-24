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
