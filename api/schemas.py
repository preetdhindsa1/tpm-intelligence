"""API response models. Every number here comes from the engine (no AI)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class ReleaseOut(_Out):
    """A release with its key dates and feature counts."""

    key: str
    name: str
    project: str = ""  # e.g. kubernetes — from release key / team connector
    display_name: str = ""  # e.g. Kubernetes — from connectors/teams/
    cycle_start_at: datetime | None
    enhancements_freeze_at: datetime | None
    code_freeze_at: datetime | None
    release_at: datetime | None
    features_in_release: int
    features_ever_in_release: int
    as_of: datetime


class FlagOut(_Out):
    """A rule flag with the facts that triggered it."""

    code: str
    severity: str
    message: str
    facts: dict[str, Any]


class OddsOut(_Out):
    """Monte Carlo odds of landing by Code Freeze. Decision support, not a guarantee."""

    status: str  # forecast | after_freeze | no_freeze_date | not_in_release
    validated: bool = False  # newest backtest beat the base rate (api/validation.py)
    base_rate: float | None = None  # earlier releases' landing rate at this lead time
    raw_probability: float | None = None  # before recalibration
    probability: float | None = None
    low: float | None = None
    high: float | None = None
    open_prs: list[str] = []
    pr_on_time: dict[str, float] = {}
    new_pr_needed: float | None = None


class PullRequestOut(_Out):
    """A verified linked PR."""

    key: str
    url: str
    title: str
    state: str
    created_at: datetime
    merged_at: datetime | None
    review_rounds: int
    review_records: int
    failing_checks: int
    freeze_status: str
    counts_for_release: bool
    is_main: bool


class TimelineEntryOut(_Out):
    """One dated fact."""

    at: datetime
    kind: str
    ref: str | None = None


class FeatureRowOut(_Out):
    """One row of the release health table."""

    key: str
    number: int
    title: str
    url: str | None
    in_release: bool
    tracked: bool
    stage: str | None
    teams: list[str]
    odds: OddsOut
    flags: list[FlagOut]
    prs_total: int
    prs_merged: int
    prs_open: int
    suggested_prs: int


class FeatureDetailOut(FeatureRowOut):
    """Feature page: everything in the row plus PRs, critical path, timeline and inputs."""

    pull_requests: list[PullRequestOut]
    suggested_pull_requests: list[str]
    critical_path: list[str]
    timeline: list[TimelineEntryOut]
    assumptions: dict[str, Any]


class FeaturesOut(_Out):
    """The release health table."""

    release: ReleaseOut
    features: list[FeatureRowOut]
    calibration: dict[str, Any]
    validation: dict[str, Any]


class LoadOut(_Out):
    """Open PRs not linked to any feature, per SIG (reviewer and CI load). Not per person."""

    release: str
    as_of: datetime
    by_sig: list[dict[str, Any]]
