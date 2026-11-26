"""Release readiness and retro API models (Wave 5, ADR-0032).

Contract: docs/api/readiness-retro-contract.md. Every number is computed by rules from stored
data; the optional summary is AI text from verified facts only, fact-checked. A person makes
the go/no-go call, and the decision log is append-only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CriterionId = Literal["code_merged", "no_critical_flags", "ci_green", "risks_owned", "docs_merged"]


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class EvidenceOut(_Out):
    """One fact behind a criterion, with a link to its source when there is one."""

    text: str
    ref: str  # e.g. "feature:kubernetes/enhancements#5419", "raid:K8S-R-002"
    url: str | None


class CriterionOut(_Out):
    """One readiness rule, configured per team (connectors/teams/<id>.yaml)."""

    id: CriterionId
    name: str
    status: Literal["pass", "fail", "unknown"]  # unknown: no data to decide, never a guess
    detail: str
    count: int | None  # how many items fail it, when countable
    evidence: list[EvidenceOut]


class ReadinessDecisionOut(_Out):
    """A person's go/no-go call. Rows are only ever appended."""

    decision: Literal["go", "no_go", "defer"]
    note: str
    decided_by: Literal["approver"]  # a role, never a login
    decided_at: datetime
    facts_as_of: datetime  # the readiness facts the person saw


class ClaimOut(_Out):
    """A fact-checked sentence of the optional AI summary."""

    text: str
    refs: list[str]


class ReadinessOut(_Out):
    project: str
    release: str
    as_of: datetime
    synthetic: bool
    # ready: every criterion passes; not_ready: any fails; unknown: none fail, some unknown.
    verdict: Literal["ready", "not_ready", "unknown"]
    criteria: list[CriterionOut]
    decisions: list[ReadinessDecisionOut]
    summary: list[ClaimOut] | None
    validated: bool  # the readiness backtest (ADR-0032); false shows "not validated"
    validation_note: str


class ReadinessDecisionIn(BaseModel):
    decision: Literal["go", "no_go", "defer"]
    note: str = Field(min_length=3, max_length=2000)


class SlipOut(_Out):
    """A feature that slipped, and when the platform first warned (as-of replay)."""

    feature_key: str
    title: str
    pool: str | None  # e.g. "sig/node"; patterns are per pool, never per person
    slip: Literal["dropped", "moved", "late_exception"]
    slipped_at: datetime
    first_warning_at: datetime | None  # None: no warning before the slip
    first_warning_flag: str | None
    lead_time_days: float | None  # slipped_at - first_warning_at
    moved_to: str | None = None  # the later release, for "moved"


class RetroSourceOut(_Out):
    kind: Literal["retro", "meeting", "snapshots", "pull_requests"]
    title: str
    url: str | None
    synthetic: bool


class RetroTotalsOut(_Out):
    slips: int
    warned: int
    average_lead_time_days: float | None
    median_lead_time_days: float | None
    planned: int | None = None  # features in the release at Enhancements Freeze or added later
    warned_landed: int | None = None  # warned but landed: false alarms, shown next to "warned"


class RetroOut(_Out):
    project: str
    release: str
    label: str  # e.g. "Kubernetes v1.37, public retro"
    as_of: datetime
    synthetic: bool
    sources: list[RetroSourceOut]
    totals: RetroTotalsOut
    slips: list[SlipOut]


class SaidItemOut(_Out):
    """A RAID item from a meeting on that date (suggested or confirmed, never hidden)."""

    item_id: int
    raid_id: str | None
    type: Literal["risk", "action", "issue", "decision", "question"]
    title: str
    review: Literal["suggested", "confirmed", "edited", "rejected"]


class ShowedFactOut(_Out):
    """A fact from the forecast snapshot of the same date."""

    name: str
    value: float | int | str | None


class SaidVsShowedRowOut(_Out):
    date: datetime
    said: list[SaidItemOut]
    showed: list[ShowedFactOut]


class SaidVsShowedOut(_Out):
    project: str
    release: str
    synthetic: bool
    rows: list[SaidVsShowedRowOut]


class PatternOut(_Out):
    """A pattern across releases for one pool, shown only for groups of 10 or more."""

    pool: str
    pattern: str  # e.g. "late_main_pr", "removed_at_freeze"
    text: str
    value: float
    n: int
    releases: list[str]


class PatternsOut(_Out):
    project: str
    synthetic: bool
    min_group: int
    suppressed_groups: int  # groups under min_group, counted but not shown
    patterns: list[PatternOut]


class LaneRetroOut(_Out):
    """One pod lane (ADR-0023), never a login. ``small_sample``: under 10 merged PRs."""

    lane: str
    opened: int
    merged: int
    still_open: int
    median_hours_to_merge: float | None
    review_rounds_median: float | None
    rework: int
    ci_failed: int
    small_sample: bool


class LaneRetroReportOut(_Out):
    project: str
    label: str
    since: datetime
    until: datetime
    as_of: datetime
    synthetic: bool
    lanes: list[LaneRetroOut]
