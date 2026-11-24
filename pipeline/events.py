"""Normalized event schema (CLAUDE.md section 3).

Collectors turn source-specific data (GitHub issues, PRs, issue events; later Jira)
into these events. Downstream code (linker, engine, forecast) depends only on this
schema, never on which source produced an event.

Design notes
------------
* One envelope, :class:`NormalizedEvent`, with a typed ``payload`` chosen by its
  ``type`` field (a Pydantic discriminated union).
* ``event_id`` is **deterministic**: re-polling the same source fact gives the same
  ID, so consumers can de-duplicate (at-least-once delivery is assumed everywhere).
* ``occurred_at`` is when the fact happened in the source system; ``observed_at`` is
  when we saw it. Backtests filter on ``occurred_at`` (CLAUDE.md section 6: only data
  dated before the prediction point).
* All timestamps must be timezone-aware and are normalized to UTC.
* Events carry only the fields the platform needs; never source code (CLAUDE.md section 10).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1

# Fixed namespace so event IDs are stable across processes and deployments.
_EVENT_NAMESPACE = uuid.UUID("5f0f3c1e-6c55-4d0b-9a57-1f0f2b3c9e01")


class Source(StrEnum):
    """System an event came from."""

    GITHUB = "github"
    JIRA = "jira"


class SubjectKind(StrEnum):
    """What the event is about."""

    WORK_ITEM = "work_item"
    PULL_REQUEST = "pull_request"
    RELEASE = "release"


class WorkItemType(StrEnum):
    """Generic work item types (CLAUDE.md section 6)."""

    INITIATIVE = "initiative"
    EPIC = "epic"
    FEATURE = "feature"
    STORY = "story"
    SUBTASK = "subtask"
    BUG = "bug"


class ChangeAction(StrEnum):
    """Direction of a membership change (label, release)."""

    ADDED = "added"
    REMOVED = "removed"


class ReviewState(StrEnum):
    """Normalized review outcome."""

    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"


class CheckConclusion(StrEnum):
    """Normalized CI result."""

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    NEUTRAL = "neutral"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SubjectRef(_Model):
    """Source-qualified reference, e.g. ``github`` / ``kubernetes/enhancements#6395``."""

    kind: SubjectKind
    source: Source
    external_key: str = Field(min_length=1)


# ---------------------------------------------------------------- payloads


class WorkItemObserved(_Model):
    """Current snapshot of a planning ticket (KEP issue, Jira epic/story)."""

    type: Literal["work_item.observed"] = "work_item.observed"
    item_type: WorkItemType
    title: str
    state: str  # source state, e.g. "open" / "In Progress"
    status_category: Literal["todo", "in_progress", "done"]
    labels: tuple[str, ...] = ()
    release_keys: tuple[str, ...] = ()  # e.g. ("kubernetes:v1.38",); see release_key()
    parent_key: str | None = None
    child_keys: tuple[str, ...] = ()  # Jira sub-tasks (an umbrella issue)
    description: str = ""  # ticket text; holds the KEP issue's PR tracking list
    url: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class WorkItemSpecObserved(_Model):
    """Design-doc metadata for a work item (KEP ``kep.yaml``; later Jira custom fields)."""

    type: Literal["work_item.spec_observed"] = "work_item.spec_observed"
    spec_path: str
    feature_flags: tuple[str, ...] = ()  # Kubernetes feature gates
    owning_team: str | None = None
    participating_teams: tuple[str, ...] = ()
    stage: str | None = None  # alpha / beta / stable
    target_release_key: str | None = None
    spec_status: str | None = None  # provisional / implementable / implemented
    # Where a Jira issue names its design doc: "title", "remote_link" or "description".
    spec_source: str | None = None


class WorkItemReleaseChanged(_Model):
    """Work item added to / removed from a release (milestoned, Jira fixVersion)."""

    type: Literal["work_item.release_changed"] = "work_item.release_changed"
    action: ChangeAction
    release_key: str


class WorkItemLabelChanged(_Model):
    """Label added / removed (e.g. ``tracked/yes`` -> ``tracked/no``)."""

    type: Literal["work_item.label_changed"] = "work_item.label_changed"
    action: ChangeAction
    label: str


class WorkItemStatusChanged(_Model):
    """Status transition (Jira workflow; GitHub open/closed)."""

    type: Literal["work_item.status_changed"] = "work_item.status_changed"
    from_state: str | None
    to_state: str
    to_category: Literal["todo", "in_progress", "done"]


class ReferenceObserved(_Model):
    """A PR referenced a work item somewhere the source records it.

    Raw evidence only; the linker decides the link method and confidence. (GitHub issue
    timelines carry no cross-reference events for KEP PRs, so this is used for Jira
    remote links only.)
    """

    type: Literal["reference.observed"] = "reference.observed"
    pull_request: SubjectRef
    evidence: Literal["remote_link"]


class CommitNote(_Model):
    """When a commit landed and its message. No diff (CLAUDE.md section 10)."""

    committed_at: AwareDatetime
    message: str = ""


class PullRequestObserved(_Model):
    """Current snapshot of a pull request (text fields only; never code)."""

    type: Literal["pull_request.observed"] = "pull_request.observed"
    repo: str
    number: int = Field(gt=0)
    title: str
    body: str = ""
    author: str | None = None
    state: Literal["open", "closed", "merged"]
    labels: tuple[str, ...] = ()
    base_ref: str | None = None
    head_sha: str | None = None
    head_ref: str | None = None
    changed_files: tuple[str, ...] = ()  # paths only
    files_truncated: bool = False  # GitHub had more than the 100 paths stored
    additions: int = 0
    deletions: int = 0
    commits: tuple[CommitNote, ...] = ()  # cap 30; messages for lane trailers
    commits_truncated: bool = False
    mergeable: Literal["mergeable", "conflicting", "unknown"] = "unknown"
    created_at: AwareDatetime
    updated_at: AwareDatetime
    merged_at: AwareDatetime | None = None
    closed_at: AwareDatetime | None = None
    url: str | None = None


class MergeabilityObserved(_Model):
    """Whether GitHub can merge the PR into its base. Can change without ``updated_at``."""

    type: Literal["pull_request.mergeability_observed"] = "pull_request.mergeability_observed"
    head_sha: str
    mergeable: Literal["mergeable", "conflicting"]


class ReviewSubmitted(_Model):
    """One review record. Review *rounds* are computed later by the engine."""

    type: Literal["pull_request.review_submitted"] = "pull_request.review_submitted"
    review_id: str
    reviewer: str | None
    state: ReviewState
    submitted_at: AwareDatetime


class CommentPosted(_Model):
    """A PR conversation comment, reduced to who, when and any Prow commands in it.

    Kubernetes reviewers approve with ``/lgtm`` and ``/approve`` comments rather than GitHub
    reviews (ADR-0006). The comment text is never stored, only the commands found in it.
    """

    type: Literal["pull_request.comment_posted"] = "pull_request.comment_posted"
    comment_id: str
    author: str | None
    posted_at: AwareDatetime
    commands: tuple[str, ...] = ()  # e.g. ("lgtm",), ("approve",), ("hold_cancel",)


class CheckCompleted(_Model):
    """CI result for a PR head commit."""

    type: Literal["pull_request.check_completed"] = "pull_request.check_completed"
    check_name: str
    head_sha: str
    conclusion: CheckConclusion
    completed_at: AwareDatetime | None = None


class ReleaseObserved(_Model):
    """Release definition with its key dates (from the checked-in calendar)."""

    type: Literal["release.observed"] = "release.observed"
    project: str
    name: str
    cycle_start_at: AwareDatetime | None = None
    enhancements_freeze_at: AwareDatetime | None = None
    code_freeze_at: AwareDatetime | None = None
    release_at: AwareDatetime | None = None
    source_url: str | None = None
    # When "landed" is judged, if not at Code Freeze (#86); 3 days are added to it.
    outcome_at: AwareDatetime | None = None


EventPayload = Annotated[
    WorkItemObserved
    | WorkItemSpecObserved
    | WorkItemReleaseChanged
    | WorkItemLabelChanged
    | WorkItemStatusChanged
    | ReferenceObserved
    | PullRequestObserved
    | MergeabilityObserved
    | ReviewSubmitted
    | CommentPosted
    | CheckCompleted
    | ReleaseObserved,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------- envelope


class NormalizedEvent(_Model):
    """Envelope for every event on the queue."""

    event_id: str
    schema_version: int = SCHEMA_VERSION
    source: Source
    subject: SubjectRef
    occurred_at: AwareDatetime
    observed_at: AwareDatetime
    payload: EventPayload

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @property
    def event_type(self) -> str:
        """The payload discriminator, e.g. ``work_item.label_changed``."""
        return self.payload.type

    def to_bytes(self) -> bytes:
        """Serialize for the queue."""
        return self.model_dump_json().encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> NormalizedEvent:
        """Parse a queued message body."""
        return cls.model_validate_json(data)


def release_key(project: str, name: str) -> str:
    """Qualified release key, e.g. ``kubernetes:v1.38`` or ``KAFKA:4.3.0``."""
    return f"{project}:{name}"


def make_event_id(source: Source, event_type: str, *identity: object) -> str:
    """Deterministic ID from the source, event type and the fact's identifying parts.

    Example: ``make_event_id(Source.GITHUB, "work_item.label_changed",
    "kubernetes/enhancements#6395", "tracked/no", "added", "2026-11-17T12:05:58Z")``.
    """
    key = "|".join([source.value, event_type, *(str(part) for part in identity)])
    return str(uuid.uuid5(_EVENT_NAMESPACE, key))


def new_event(
    *,
    source: Source,
    subject: SubjectRef,
    occurred_at: datetime,
    payload: EventPayload,
    identity: tuple[object, ...],
    observed_at: datetime | None = None,
) -> NormalizedEvent:
    """Build an event whose ID is derived from ``source``, payload type and ``identity``."""
    return NormalizedEvent(
        event_id=make_event_id(source, payload.type, subject.external_key, *identity),
        source=source,
        subject=subject,
        occurred_at=occurred_at,
        observed_at=observed_at or datetime.now(UTC),
        payload=payload,
    )
