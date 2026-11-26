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
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
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


class RiskNoteRecord(Base):
    """A verified risk note for one feature (only verified claims are stored)."""

    __tablename__ = "risk_notes"
    __table_args__ = (Index(None, "release_key", "feature_key", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    release_key: Mapped[str] = mapped_column(String(128))
    feature_key: Mapped[str] = mapped_column(String(256))
    prompt_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    facts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    counts: Mapped[dict[str, int]] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())


UPDATE_STATUSES = ("draft", "approved", "rejected")


class ExecUpdateRecord(Base):
    """An executive update draft and its approval (the platform never sends it)."""

    __tablename__ = "exec_updates"
    __table_args__ = (
        CheckConstraint(_in("status", UPDATE_STATUSES), name="status"),
        Index(None, "release_key", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    release_key: Mapped[str] = mapped_column(String(128))
    as_of: Mapped[datetime] = mapped_column(_tz())
    header: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sections: Mapped[dict[str, Any]] = mapped_column(JSONB)
    facts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    counts: Mapped[dict[str, int]] = mapped_column(JSONB)
    removed: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    trimmed_for_length: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(16))
    edited: Mapped[bool] = mapped_column(server_default="false")
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decided_at: Mapped[datetime | None] = mapped_column(_tz())
    decision_note: Mapped[str | None] = mapped_column(Text)
    approved_with_warnings: Mapped[bool] = mapped_column(server_default="false")
    approved_while_stale: Mapped[bool] = mapped_column(server_default="false")
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())


SUGGESTION_STATUSES = ("suggested", "confirmed", "rejected", "none", "dropped")


class LinkSuggestionRecord(Base):
    """One AI link-suggester answer for an unlinked PR, and a person's decision (ADR-0011).

    Only ``confirmed`` rows become verified links, and only with ``decided_by`` set
    (CLAUDE.md section 2.2). ``none`` and ``dropped`` rows record that the PR was looked at.
    """

    __tablename__ = "link_suggestions"
    __table_args__ = (
        CheckConstraint(_in("status", SUGGESTION_STATUSES), name="status"),
        CheckConstraint(
            "status NOT IN ('confirmed', 'rejected') OR "
            "(decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="decision_has_person",
        ),
        CheckConstraint(
            "status NOT IN ('suggested', 'confirmed', 'rejected') OR feature_key IS NOT NULL",
            name="link_has_feature",
        ),
        UniqueConstraint(
            "release_key",
            "pull_request_key",
            "input_sha",
            "prompt_version",
            name="uq_link_suggestions_input",  # the generated name passes Postgres's 63 chars
        ),
        Index(None, "release_key", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    release_key: Mapped[str] = mapped_column(String(128))
    pull_request_key: Mapped[str] = mapped_column(String(256))
    feature_key: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    input_sha: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decided_at: Mapped[datetime | None] = mapped_column(_tz())
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())


class SimCalibrationRecord(Base):
    """A fitted simulator calibration for one release (ADR-0012, CLAUDE.md section 14).

    Stored with its source releases, measurement date and validation result, so every
    scenario result can show the inputs it used. ``body`` holds the measured inputs,
    including the real PR paths (no names, no PR text).
    """

    __tablename__ = "sim_calibrations"
    __table_args__ = (Index(None, "release_key", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    release_key: Mapped[str] = mapped_column(String(128))
    source_releases: Mapped[list[str]] = mapped_column(ARRAY(Text))
    measured_at: Mapped[datetime] = mapped_column(_tz())
    validated: Mapped[bool] = mapped_column(Boolean)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())


class SimScenarioRecord(Base):
    """A saved what-if and its result, named per release (ADR-0012)."""

    __tablename__ = "sim_scenarios"
    __table_args__ = (UniqueConstraint("release_key", "name"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    release_key: Mapped[str] = mapped_column(String(128))
    calibration_id: Mapped[int] = mapped_column(ForeignKey("sim_calibrations.id"))
    name: Mapped[str] = mapped_column(String(128))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())


class ForecastSnapshotRunRecord(Base):
    """One day's recorded forecast of a release (ADR-0015). Never updated or deleted.

    ``body`` holds the model settings, calibration inputs, validation labels and the
    release curve, so a later score can show exactly what was predicted and how.
    """

    __tablename__ = "forecast_snapshot_runs"
    __table_args__ = (UniqueConstraint("release_key", "snapshot_date", "model_version"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    release_key: Mapped[str] = mapped_column(String(128))
    snapshot_date: Mapped[date] = mapped_column(Date)
    as_of: Mapped[datetime] = mapped_column(_tz())
    model_version: Mapped[str] = mapped_column(String(64))
    code_freeze_at: Mapped[datetime | None] = mapped_column(_tz())
    release_at: Mapped[datetime | None] = mapped_column(_tz())
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())


class ForecastSnapshotRecord(Base):
    """One feature's recorded odds and merge-date forecast in a snapshot run (ADR-0015)."""

    __tablename__ = "forecast_snapshots"
    __table_args__ = (UniqueConstraint("run_id", "feature_key"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_snapshot_runs.id"))
    feature_key: Mapped[str] = mapped_column(String(128))
    in_release: Mapped[bool] = mapped_column(Boolean)
    odds_status: Mapped[str] = mapped_column(String(32))
    probability: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    raw_probability: Mapped[float | None] = mapped_column(Float)
    merge_status: Mapped[str] = mapped_column(String(32))
    done_day: Mapped[float | None] = mapped_column(Float)
    p10: Mapped[float | None] = mapped_column(Float)
    p50: Mapped[float | None] = mapped_column(Float)
    p90: Mapped[float | None] = mapped_column(Float)
    by_freeze: Mapped[float | None] = mapped_column(Float)
    by_release: Mapped[float | None] = mapped_column(Float)
    # [day, P(merged by day), low, high] for scoring merge dates later (CRPS).
    cdf: Mapped[list[Any]] = mapped_column(JSONB)


class RaidItemRecord(Base):
    """A RAID item (migration 0010, ADR-0030 addendum 2). Logic: ``modules.raid``."""

    __tablename__ = "raid_items"
    __table_args__ = (
        CheckConstraint(_in("type", ("risk", "action", "issue", "decision", "question")),
                        name="type"),
        CheckConstraint(_in("status", ("open", "in_progress", "closed", "superseded")),
                        name="status"),
        CheckConstraint(_in("review", ("suggested", "confirmed", "edited", "rejected")),
                        name="review"),
        CheckConstraint("(review IN ('confirmed', 'edited')) = (raid_id IS NOT NULL)",
                        name="id_on_confirm"),
        Index("ix_raid_items_release_key", "release_key", "review"),
    )  # fmt: skip

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    release_key: Mapped[str] = mapped_column(String(128))
    workstream: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    document_id: Mapped[str] = mapped_column(String(128))
    meeting_date: Mapped[str] = mapped_column(String(10))
    owner: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), server_default="open")
    review: Mapped[str] = mapped_column(String(16), server_default="suggested")
    raid_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    links: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    merge_into: Mapped[int | None] = mapped_column(ForeignKey("raid_items.id"))
    merge_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())


class RaidHistoryRecord(Base):
    """One append-only change to a RAID item. ``by_login`` is for audit, never shown."""

    __tablename__ = "raid_history"
    __table_args__ = (
        CheckConstraint(_in("actor", ("extractor", "approver")), name="actor"),
        CheckConstraint("action <> 'rejected' OR length(trim(coalesce(reason, ''))) > 0",
                        name="reject_reason"),
        Index("ix_raid_history_item_id", "item_id", "id"),
    )  # fmt: skip

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("raid_items.id"))
    at: Mapped[datetime] = mapped_column(_tz())
    actor: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(16))
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    reason: Mapped[str | None] = mapped_column(Text)
    by_login: Mapped[str | None] = mapped_column(String(64))


class ReadinessDecisionRecord(Base):
    """A go/no-go call (migration 0011, ADR-0032). Append-only; ``by_login`` is audit only."""

    __tablename__ = "readiness_decisions"
    __table_args__ = (
        CheckConstraint(_in("decision", ("go", "no_go", "defer")), name="decision"),
        CheckConstraint("length(trim(note)) >= 3", name="note"),
        Index("ix_readiness_decisions_release_key", "release_key", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    release_key: Mapped[str] = mapped_column(String(128))
    decision: Mapped[str] = mapped_column(String(8))
    note: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(_tz())
    facts_as_of: Mapped[datetime] = mapped_column(_tz())
    verdict: Mapped[str] = mapped_column(String(16))
    by_login: Mapped[str] = mapped_column(String(64))


class RetroRunRecord(Base):
    """One computed retro (migration 0012, ADR-0032 addendum 2). Append-only."""

    __tablename__ = "retro_runs"
    __table_args__ = (Index("ix_retro_runs_release_key", "release_key", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    release_key: Mapped[str] = mapped_column(String(128))
    computed_at: Mapped[datetime] = mapped_column(_tz())
    model_version: Mapped[str] = mapped_column(String(32))
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
