"""Postgres schema (source of truth). See ADR-0002.

Conventions
-----------
* All timestamps are ``timestamptz``. Source-system times use the ``*_at`` names of the
  source (``created_at``, ``merged_at``); our own bookkeeping uses ``first_seen_at`` /
  ``last_seen_at`` / ``ingested_at``.
* Enumerations are ``text`` + ``CHECK`` constraints, not Postgres enums, so adding a value
  is a one-line migration.
* ``events`` is append-only (enforced by a trigger in the migration). Current-state tables
  (``work_items``, ``work_item_releases``, ...) are projections that can be rebuilt from it.
* Never store source code (CLAUDE.md section 10): PRs keep title/body/labels only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from linker.methods import LinkMethod, LinkStatus
from pipeline.events import (
    CheckConclusion,
    ReviewState,
    Source,
    SubjectKind,
    WorkItemType,
)

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

STATUS_CATEGORIES = ("todo", "in_progress", "done")
MEMBERSHIP_STATUSES = ("active", "removed")
PR_STATES = ("open", "closed", "merged")
RELATION_KINDS = ("blocks", "depends_on", "relates_to", "duplicates")


def _in(column: str, values: Any) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _tz() -> DateTime:
    return DateTime(timezone=True)


class Base(DeclarativeBase):
    """Declarative base with stable constraint names (needed for clean migrations)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class _Timestamps:
    first_seen_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        _tz(), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------- planning side


class Release(_Timestamps, Base):
    """A release (Kubernetes ``v1.38``, Jira fix version ``4.3.0``) and its key dates."""

    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("source", "project", "name"),
        CheckConstraint(_in("source", [s.value for s in Source]), name="source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    project: Mapped[str] = mapped_column(String(128))  # "kubernetes", "KAFKA"
    name: Mapped[str] = mapped_column(String(64))  # "v1.38", "4.3.0"
    enhancements_freeze_at: Mapped[datetime | None] = mapped_column(_tz())
    code_freeze_at: Mapped[datetime | None] = mapped_column(_tz())
    release_at: Mapped[datetime | None] = mapped_column(_tz())
    source_url: Mapped[str | None] = mapped_column(Text)


class WorkItem(_Timestamps, Base):
    """Generic planning ticket: KEP issue, Jira initiative/epic/story/... (CLAUDE.md section 6)."""

    __tablename__ = "work_items"
    __table_args__ = (
        UniqueConstraint("source", "external_key"),
        CheckConstraint(_in("source", [s.value for s in Source]), name="source"),
        CheckConstraint(_in("type", [t.value for t in WorkItemType]), name="type"),
        CheckConstraint(_in("status_category", STATUS_CATEGORIES), name="status_category"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        Index(None, "parent_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    external_key: Mapped[str] = mapped_column(String(256))  # "kubernetes/enhancements#6395"
    type: Mapped[str] = mapped_column(String(16))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(64))  # source state: "open", "In Progress"
    status_category: Mapped[str] = mapped_column(String(16))
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_tz())
    updated_at: Mapped[datetime] = mapped_column(_tz())

    parent: Mapped[WorkItem | None] = relationship(remote_side=[id])
    releases: Mapped[list[WorkItemRelease]] = relationship(
        back_populates="work_item", cascade="all, delete-orphan", passive_deletes=True
    )


class WorkItemRelease(Base):
    """Many-to-many work item <-> release (KAFKA-21181 has four fix versions).

    ``status='removed'`` keeps the row for history but drops it from current-state
    queries (CLAUDE.md section 6: removed items disappear from current-state searches).
    """

    __tablename__ = "work_item_releases"
    __table_args__ = (
        CheckConstraint(_in("status", MEMBERSHIP_STATUSES), name="status"),
        CheckConstraint(
            "(status = 'removed') = (removed_at IS NOT NULL)", name="removed_at_matches_status"
        ),
        Index(None, "release_id", "status"),
    )

    work_item_id: Mapped[int] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), primary_key=True
    )
    release_id: Mapped[int] = mapped_column(
        ForeignKey("releases.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    added_at: Mapped[datetime] = mapped_column(_tz())  # source time of the latest add
    removed_at: Mapped[datetime | None] = mapped_column(_tz())

    work_item: Mapped[WorkItem] = relationship(back_populates="releases")
    release: Mapped[Release] = relationship()


class WorkItemRelation(Base):
    """Work item -> work item dependency (e.g. KAFKA-19831 links to KAFKA-17789)."""

    __tablename__ = "work_item_relations"
    __table_args__ = (
        UniqueConstraint("from_id", "to_id", "kind"),
        CheckConstraint(_in("kind", RELATION_KINDS), name="kind"),
        CheckConstraint("from_id <> to_id", name="no_self_relation"),
        CheckConstraint(_in("status", [s.value for s in LinkStatus]), name="status"),
        Index(None, "to_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"))
    to_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())


# ---------------------------------------------------------------- code side


class PullRequest(_Timestamps, Base):
    """A pull request: text fields and timestamps only, never code."""

    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repo", "number"),
        CheckConstraint(_in("source", [s.value for s in Source]), name="source"),
        CheckConstraint(_in("state", PR_STATES), name="state"),
        CheckConstraint("(state = 'merged') = (merged_at IS NOT NULL)", name="merged_at_state"),
        Index(None, "merged_at"),
        Index(None, "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), server_default=Source.GITHUB.value)
    repo: Mapped[str] = mapped_column(String(256))  # "kubernetes/kubernetes"
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, server_default="")
    author: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(16))
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    base_ref: Mapped[str | None] = mapped_column(String(256))
    head_sha: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_tz())
    updated_at: Mapped[datetime] = mapped_column(_tz())
    merged_at: Mapped[datetime | None] = mapped_column(_tz())
    closed_at: Mapped[datetime | None] = mapped_column(_tz())

    # Children are removed by ON DELETE CASCADE in the database; passive_deletes stops the
    # ORM from trying to NULL their foreign keys first.
    reviews: Mapped[list[Review]] = relationship(
        back_populates="pull_request", cascade="all, delete-orphan", passive_deletes=True
    )
    links: Mapped[list[Link]] = relationship(
        back_populates="pull_request", cascade="all, delete-orphan", passive_deletes=True
    )


class Review(Base):
    """One raw review record. Rounds are derived in ``review_rounds`` (ADR-0006)."""

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("pull_request_id", "external_id"),
        CheckConstraint(_in("state", [s.value for s in ReviewState]), name="state"),
        Index(None, "pull_request_id", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(128))
    reviewer: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(32))
    submitted_at: Mapped[datetime] = mapped_column(_tz())

    pull_request: Mapped[PullRequest] = relationship(back_populates="reviews")


class ReviewRound(Base):
    """Reviews by one reviewer grouped within a time window (computed by the engine)."""

    __tablename__ = "review_rounds"
    __table_args__ = (
        UniqueConstraint("pull_request_id", "reviewer", "started_at"),
        CheckConstraint("ended_at >= started_at", name="ordered"),
        CheckConstraint("review_count >= 1", name="non_empty"),
        CheckConstraint(_in("outcome", [s.value for s in ReviewState]), name="outcome"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"))
    reviewer: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(_tz())
    ended_at: Mapped[datetime] = mapped_column(_tz())
    review_count: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32))  # strongest state in the round
    window_minutes: Mapped[int] = mapped_column(Integer)  # grouping parameter used


class CheckRun(Base):
    """CI result for a PR head commit."""

    __tablename__ = "check_runs"
    __table_args__ = (
        UniqueConstraint("pull_request_id", "check_name", "head_sha"),
        CheckConstraint(_in("conclusion", [c.value for c in CheckConclusion]), name="conclusion"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"))
    check_name: Mapped[str] = mapped_column(String(256))
    head_sha: Mapped[str] = mapped_column(String(64))
    conclusion: Mapped[str] = mapped_column(String(16))
    completed_at: Mapped[datetime | None] = mapped_column(_tz())


# ---------------------------------------------------------------- links


class Link(Base):
    """PR -> work item link with method, confidence and status (CLAUDE.md section 6).

    Database guard: an ``ai_suggested`` link can only be ``verified`` when
    ``verified_by`` names the rule or person who confirmed it (CLAUDE.md section 2.2).
    """

    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint("pull_request_id", "work_item_id", "method"),
        CheckConstraint(_in("method", [m.value for m in LinkMethod]), name="method"),
        CheckConstraint(_in("status", [s.value for s in LinkStatus]), name="status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "status <> 'verified' OR method <> 'ai_suggested' OR verified_by IS NOT NULL",
            name="ai_links_need_verifier",
        ),
        CheckConstraint(
            "(verified_by IS NULL) = (verified_at IS NULL)", name="verifier_has_timestamp"
        ),
        Index(None, "work_item_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"))
    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"))
    method: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    status: Mapped[str] = mapped_column(String(16))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    verified_by: Mapped[str | None] = mapped_column(String(128))  # "rule:<name>" / "user:<login>"
    verified_at: Mapped[datetime | None] = mapped_column(_tz())

    pull_request: Mapped[PullRequest] = relationship(back_populates="links")
    work_item: Mapped[WorkItem] = relationship()


# ---------------------------------------------------------------- history


class EventRecord(Base):
    """Append-only log of every normalized event. Backtests read only from here."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(_in("source", [s.value for s in Source]), name="source"),
        CheckConstraint(_in("subject_kind", [k.value for k in SubjectKind]), name="subject_kind"),
        Index(None, "subject_kind", "subject_key", "occurred_at"),
        Index(None, "occurred_at"),
        Index(None, "event_type", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))
    subject_kind: Mapped[str] = mapped_column(String(16))
    subject_key: Mapped[str] = mapped_column(String(256))
    occurred_at: Mapped[datetime] = mapped_column(_tz())
    observed_at: Mapped[datetime] = mapped_column(_tz())
    ingested_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Snapshot(Base):
    """Point-in-time copy of computed state (e.g. a forecast as it was on a date)."""

    __tablename__ = "snapshots"
    __table_args__ = (
        UniqueConstraint("kind", "subject_kind", "subject_key", "as_of"),
        CheckConstraint(_in("subject_kind", [k.value for k in SubjectKind]), name="subject_kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))  # "work_item_state", "forecast"
    subject_kind: Mapped[str] = mapped_column(String(16))
    subject_key: Mapped[str] = mapped_column(String(256))
    as_of: Mapped[datetime] = mapped_column(_tz())  # data cut-off the snapshot reflects
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class SyncCursor(Base):
    """Incremental sync position per collector stream, plus health for alerting."""

    __tablename__ = "sync_cursors"
    __table_args__ = (CheckConstraint("consecutive_failures >= 0", name="failures_non_negative"),)

    stream: Mapped[str] = mapped_column(String(256), primary_key=True)
    cursor: Mapped[str | None] = mapped_column(Text)  # e.g. max updated_at seen
    last_attempt_at: Mapped[datetime | None] = mapped_column(_tz())
    last_success_at: Mapped[datetime | None] = mapped_column(_tz())
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)


AI_OUTCOMES = ("ok", "refused", "max_tokens", "error", "budget_denied", "cache_hit")


class AIUsage(Base):
    """One AI call attempt: tokens, cost and outcome. Sums per UTC day enforce the budget."""

    __tablename__ = "ai_usage"
    __table_args__ = (
        CheckConstraint(_in("outcome", AI_OUTCOMES), name="outcome"),
        Index(None, "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    task: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    model_requested: Mapped[str] = mapped_column(String(64))
    model_served: Mapped[str | None] = mapped_column(String(64))
    essential: Mapped[bool]
    outcome: Mapped[str] = mapped_column(String(16))
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cache_read_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cache_write_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default="0")
    fingerprint: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[str | None] = mapped_column(Text)


class AIResult(Base):
    """Cached structured output by input fingerprint, with its fact-check counts."""

    __tablename__ = "ai_results"

    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    task: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    output: Mapped[dict[str, Any]] = mapped_column(JSONB)
    check_counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
