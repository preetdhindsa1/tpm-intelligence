"""API response models. Every number here comes from the engine (no AI)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    has_lab: bool = False
    code_freeze_label: str = "Code Freeze"  # the team's name for its code_freeze date


class FlagOut(_Out):
    """A rule flag with the facts that triggered it."""

    code: str
    severity: str
    message: str
    facts: dict[str, Any]


class OddsOut(_Out):
    """Monte Carlo odds of landing by Code Freeze. Decision support, not a guarantee."""

    status: str  # forecast | after_freeze | no_freeze_date | insufficient_history | not_in_release
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


class MergeDateOut(_Out):
    """When a feature's required code merges, in days relative to Code Freeze (ADR-0005)."""

    feature_key: str
    status: str  # done | forecast | no_freeze_date | insufficient_history
    done_day: float | None = None
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    by_freeze: float | None = None
    by_release: float | None = None
    # [day, P(merged by day), low, high]
    cdf: list[tuple[int, float, float, float]] = []


class FeatureDetailOut(FeatureRowOut):
    """Feature page: everything in the row plus PRs, critical path, timeline and inputs."""

    pull_requests: list[PullRequestOut]
    suggested_pull_requests: list[str]
    critical_path: list[str]
    timeline: list[TimelineEntryOut]
    assumptions: dict[str, Any]
    merge_date: MergeDateOut | None = None
    merge_date_validation: dict[str, Any] = {}


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


class ClaimOutApi(BaseModel):
    """One verified claim and the facts it cites."""

    text: str
    type: str
    refs: list[str]
    value: Any = None


class RiskNoteOut(BaseModel):
    """Why a feature is at risk: AI-written, every claim verified against engine facts."""

    status: str  # not_at_risk | fresh | reused | stale | paused | failed
    reason: str | None = None
    claims: list[ClaimOutApi] = []
    claims_removed: int = 0  # by the fact checker, best attempt
    removed_by_reason: dict[str, int] = {}
    attempts: int = 0
    model: str | None = None
    prompt_version: str | None = None
    generated_at: datetime | None = None
    cost_usd: float | None = None
    odds_validated: bool | None = None


class UpdateWarningOut(BaseModel):
    """An edited claim that fails the fact check."""

    section: str
    text: str
    reason: str
    detail: str | None = None


class ExecUpdateOut(BaseModel):
    """An executive update. AI sections hold only verified (or TPM-edited) claims."""

    id: int
    release: str
    status: str  # draft | approved | rejected
    stale: bool
    header: dict[str, Any]
    sections: dict[str, list[ClaimOutApi]]
    word_count: int
    claims_removed: int
    removed: list[dict[str, Any]]
    trimmed_for_length: int
    attempts: int
    model: str
    prompt_version: str
    cost_usd: float
    edited: bool
    warnings: list[UpdateWarningOut]
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    approved_with_warnings: bool = False
    approved_while_stale: bool = False
    created_at: datetime
    markdown: str


class ClaimIn(BaseModel):
    """A claim as edited by the TPM (refs, type and value come from the draft)."""

    text: str
    type: str
    refs: list[str]
    value: Any = None


class UpdateEditIn(BaseModel):
    """Replace a draft's sections."""

    sections: dict[str, list[ClaimIn]]


class DecisionIn(BaseModel):
    """Approve or reject."""

    acknowledge_warnings: bool = False
    acknowledge_stale: bool = False
    note: str | None = None


class LinkSuggestionOut(BaseModel):
    """One AI link suggestion in the review queue (ADR-0011)."""

    id: int
    status: str  # suggested | confirmed | rejected
    pull_request: str
    pull_request_title: str | None
    pull_request_url: str | None
    pull_request_state: str | None
    feature: str
    feature_number: int | None
    feature_title: str | None
    pr_quote: str
    feature_quote: str
    shortlist_rank: int | None
    shortlist_size: int | None
    model: str
    prompt_version: str
    created_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None


class LinkSuggestionsOut(BaseModel):
    """The queue plus what the suggester has done for the release."""

    release: str
    counts: dict[str, int]  # per status, incl. none and dropped
    cost_usd: float
    suggestions: list[LinkSuggestionOut]


class LinkDecisionIn(BaseModel):
    """Confirm or reject a suggestion."""

    note: str | None = None


# ---- simulator (ADR-0012) -----------------------------------------------------------------


class PoolChangeIn(BaseModel):
    """A change to one reviewer pool. Defaults mean "no change"."""

    reviewers: int = Field(0, ge=-50, le=50)
    new_reviewers: int = Field(0, ge=0, le=50)
    ramp_weeks: float = Field(0.0, ge=0, le=52)
    interruption: float = Field(0.0, ge=0, le=0.9)


class ScenarioIn(BaseModel):
    """A what-if. ``name`` is required only to save it."""

    name: str = Field("", max_length=128)
    pools: dict[str, PoolChangeIn] = Field(default_factory=dict)
    arrival_multiplier: float = Field(1.0, ge=0, le=3)


class RangeOut(_Out):
    """Median and 10th-90th percentile over replications."""

    median: float
    low: float
    high: float


class PoolOutcomeOut(_Out):
    """One pool (or ``all``) at the horizon."""

    pool: str
    reviewers: int | None
    review_wait_days: RangeOut | None
    merged: RangeOut | None
    not_merged: RangeOut | None


class OutcomeOut(_Out):
    """One scenario's result."""

    scenario: dict[str, Any]
    pools: list[PoolOutcomeOut]
    total: PoolOutcomeOut


class SimPoolOut(_Out):
    """Measured and fitted inputs of one pool, shown as the result's assumptions."""

    pool: str
    prs_measured: int
    arrivals_per_week: float
    reviewers_per_week_source: float  # median over the source releases
    reviewers_now: int  # this release's measured reviewers per week, rounded
    open_prs_now: int
    first_wait_median_days: float | None
    follow_wait_median_days: float | None
    first_scale: float
    later_scale: float


class SimulatorOut(_Out):
    """What the simulator would run on, and whether it is validated."""

    release: str
    validated: bool
    validation: dict[str, Any]
    calibration_id: int
    calibrated_at: datetime
    source_releases: list[str]
    data_until: datetime
    effort_days: float
    as_of: datetime
    horizon_at: datetime
    horizon_label: str
    replications: int
    pools: list[SimPoolOut]
    note: str


class SimulationOut(_Out):
    """Baseline next to a scenario (CLAUDE.md section 14)."""

    release: str
    validated: bool
    calibration_id: int
    source_releases: list[str]
    as_of: datetime
    horizon_at: datetime
    horizon_label: str
    replications: int
    seed: int
    baseline: OutcomeOut
    scenario: OutcomeOut
    seconds: float
    note: str


class SavedScenarioOut(_Out):
    """A saved scenario with the result it had when saved."""

    id: int
    name: str
    created_by: str
    created_at: datetime
    calibration_id: int
    settings: dict[str, Any]
    result: SimulationOut


# ---- dashboard (ADR-0013) -------------------------------------------------------------------


class GraphNodeOut(_Out):
    """A node of the release dependency graph (engine/graph.py)."""

    id: str
    kind: str  # release | feature | pull_request
    label: str
    title: str
    url: str | None = None
    sigs: list[str] = []
    in_release: bool | None = None  # features
    severity: str | None = None  # highest flag severity (features)
    flags: list[str] = []
    state: str | None = None  # PRs: open | merged | closed
    is_main: bool | None = None
    on_critical_path: bool = False
    feature: str | None = None  # PRs: the feature they implement (first one)


class GraphEdgeOut(_Out):
    """contains (release -> feature), implemented_by (feature -> PR), blocks (PR -> PR)."""

    source: str
    target: str
    kind: str


class GraphOut(_Out):
    """Release graph with verified links only."""

    release: str
    as_of: datetime
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class FeatureOutcomeOut(_Out):
    """What happened to one feature at Code Freeze (facts), or that it is too early."""

    key: str
    number: int
    title: str
    outcome: str
    sigs: list[str]


class SourceFreshnessOut(_Out):
    """One collector source of a release (ADR-0036). Never its error text."""

    kind: str  # planning | code
    system: str  # github | jira
    last_success_at: datetime | None
    age_minutes: float | None
    consecutive_failures: int
    stale: bool
    stale_after_minutes: int


class FreshnessOut(_Out):
    """How old a release's data is: fresh | stale | final | unknown (ADR-0036)."""

    release: str
    status: str
    as_of: datetime | None  # the stalest source's last successful sync
    checked_at: datetime
    sources: list[SourceFreshnessOut]


class SummaryOut(_Out):
    """Stat tiles and outcome counts for the dashboard. All computed facts."""

    release: str
    as_of: datetime
    phase: str  # before_freeze | after_freeze
    features_in_release: int
    features_ever: int
    landed: int | None  # None before the outcome is known
    removed_at_freeze: int
    critical_features: int
    open_linked_prs: int
    unlinked_open_prs: int
    outcomes: dict[str, int]
    features: list[FeatureOutcomeOut]


class DepPROut(_Out):
    """A verified PR of a feature on the dependencies page."""

    key: str
    number: int
    title: str
    url: str
    state: str  # open | merged | closed
    is_main: bool
    freeze_status: str


class DepFeatureOut(_Out):
    """A feature on the dependencies page."""

    key: str
    number: int
    title: str
    url: str | None
    sigs: list[str]
    in_release: bool
    severity: str | None
    flags: list[str]
    outcome: str
    cluster: int | None  # index into ``clusters``; None = stand-alone
    prs: list[DepPROut]


class StatedDependencyOut(_Out):
    """A PR of ``downstream`` says it depends on a PR only ``upstream`` owns."""

    upstream: str
    downstream: str
    blocker: str
    dependent: str


class CouplingOut(_Out):
    """Two features tied by shared PRs (shared code) and/or stated dependencies."""

    a: str
    b: str
    shared_prs: list[str]
    stated: list[StatedDependencyOut]


class WaitingPROut(_Out):
    """An open PR that says it depends on a PR that has not merged."""

    pr: str
    pr_title: str
    waits_on: str
    waits_on_title: str
    waits_on_state: str
    features: list[str]


class SigPairOut(_Out):
    """Features owned by both SIGs (coordination load). Per SIG, never per person."""

    a: str
    b: str
    features: int


class DependenciesOut(_Out):
    """Feature-to-feature dependencies from verified links and PR text (engine/graph.py)."""

    release: str
    as_of: datetime
    include_removed: bool
    features: list[DepFeatureOut]
    pr_edges: list[GraphEdgeOut]  # blocks edges between the PRs listed above
    couplings: list[CouplingOut]
    clusters: list[list[str]]
    waiting: list[WaitingPROut]
    sig_pairs: list[SigPairOut]


class CurveFeatureOut(_Out):
    """One feature on the days-of-delay chart."""

    key: str
    number: int
    title: str
    status: str
    done_day: float | None
    p10: float | None
    p50: float | None
    p90: float | None
    by_release: float | None


class MergeDatesOut(_Out):
    """Days-of-delay chart: features with required code merged, by day (ADR-0005)."""

    release: str
    as_of: datetime
    code_freeze_at: datetime | None
    release_at: datetime | None
    as_of_day: float | None
    release_day: float | None
    features: int
    done_now: int
    # [day relative to Code Freeze, expected count, low, high]
    forecast: list[tuple[int, float, float, float]]
    # [day, count] of features whose required code had merged by that day
    actual: list[tuple[int, int]]
    items: list[CurveFeatureOut]
    validation: dict[str, Any]
    note: str


class SnapshotRunOut(_Out):
    """One day's recorded forecast."""

    snapshot_date: date
    as_of: datetime
    model_version: str
    features: int


class SnapshotsOut(_Out):
    """Forecasts recorded for a release (append-only; ADR-0015)."""

    release: str
    current_model_version: str
    runs: list[SnapshotRunOut]


class MeOut(_Out):
    """The person the web app is acting for (ADR-0016)."""

    login: str | None
    signed_in: bool
    approver: bool
    mode: str  # required | local


class LabWeekOut(_Out):
    week: str
    lane: str
    count: int


class LabDayOut(_Out):
    day: str
    count: int


class LabCollisionOut(_Out):
    kind: str
    pull_requests: list[str]
    paths: list[str]
    truncated: bool


class LabCapOut(_Out):
    observed_max_open: int
    held: int | None
    scenario_max_open: int | None
    comparable: bool
    assumption: str


class LabFirstPassOut(_Out):
    observed_median_hours: float | None
    n: int
    waiting: int
    comparable: bool
    assumption: str


class LabSizeOut(_Out):
    over_cap: int
    extra_pull_requests: int | None
    comparable: bool
    assumption: str


class LabBucketOut(_Out):
    lane: str
    opened: int
    merged: int
    still_open: int


class PodMemberOut(_Out):
    """One pod member: a lane (human, claude, cursor) or the Dependabot bot lane."""

    lane: str
    kind: str  # owner | agent | bot
    opened: int
    merged: int
    closed_unmerged: int
    open: int
    median_minutes_to_merge: int | None  # null below 5 merged PRs (R22)


class PodStageOut(_Out):
    """One of the 7 pod-flow stages."""

    stage: str
    rules: str
    status: str  # held | broken | not_measured
    value: dict[str, int | None] | None
    reason: str | None


class PodMetricOut(_Out):
    """A pod metric against its starting target."""

    metric: str
    target: str
    value: float | None
    unit: str
    reason: str | None


class PodRuleOut(_Out):
    """A pod rule checked against real PRs."""

    rule: str
    title: str
    status: str  # held | broken | not_measured
    count: int | None  # PRs that break it
    of: int | None  # PRs it applies to


class PodOut(_Out):
    """Pod facts (ADR-0023 addendum 2). Reviews are attributed by marker, never by login."""

    members: list[PodMemberOut]
    no_lane: int
    flow: list[PodStageOut]
    metrics: list[PodMetricOut]
    rules: list[PodRuleOut]


class LabOut(_Out):
    """Development-lab counts. A case study, not a forecast."""

    release: str
    project: str
    lanes_configured: bool
    as_of: datetime
    n_pull_requests: int
    n_merged: int
    n_open: int
    small_sample: bool
    buckets: list[LabBucketOut]
    approval_rate: float | None
    approved_merged: int
    median_hours_to_merge: float | None
    arrivals: list[LabWeekOut]
    queue: list[LabDayOut]
    time_to_first_review_hours: list[float]
    still_waiting: int
    review_round_counts: list[int]
    review_rounds_median: float | None
    rework: int
    ci_failures: int
    collisions: list[LabCollisionOut]
    cap: LabCapOut
    first_pass: LabFirstPassOut
    size: LabSizeOut
    pod: PodOut | None = None


class PortfolioMilestoneOut(_Out):
    """A named calendar date."""

    name: str
    at: datetime


class PortfolioStageOut(_Out):
    """Calendar stage (ADR-0025 rule 2)."""

    current: str | None
    stages: list[dict[str, str]]
    last_milestone: PortfolioMilestoneOut | None
    next_milestone: PortfolioMilestoneOut | None
    days_to_next_milestone: int | None


class PortfolioBottleneckOut(_Out):
    """The first bottleneck rule that fires (ADR-0025 rule 4)."""

    kind: str
    severity: str
    headline: str
    detail: str | None
    facts: dict[str, Any]


class PortfolioDecisionOut(_Out):
    """A decision waiting on a person."""

    kind: str
    label: str
    count: int
    ref: dict[str, int] | None


class PortfolioItemOut(PortfolioDecisionOut):
    """A decision waiting on a person, with its program."""

    program_key: str


class PortfolioProgramOut(_Out):
    """One Portfolio row."""

    key: str
    project: str
    display_name: str
    release: str
    planning_tool: str
    code_tools: list[str]
    has_lab: bool
    has_retro: bool = False
    code_freeze_label: str
    as_of: datetime
    dates: dict[str, datetime | None]
    stage: PortfolioStageOut
    scope: dict[str, int]
    bottleneck: PortfolioBottleneckOut
    next_decision: PortfolioDecisionOut | None


class PortfolioOut(_Out):
    """GET /portfolio (docs/api/ux-v1-contract.md, ADR-0025)."""

    as_of: datetime
    totals: dict[str, Any]
    programs: list[PortfolioProgramOut]
    waiting_on_you: list[PortfolioItemOut]
    across_programs: list[dict[str, Any]]
    coming_next: list[dict[str, Any]]
    skipped: list[dict[str, str]]
