"""What-if scenarios from today until the next milestone (ADR-0012). Pure, no I/O.

The simulator is **not validated** (ADR-0012): every result built here must be shown with
that label, and as decision support only (CLAUDE.md §14).

* **Calibration** (``Calibration``): inputs measured on finished releases plus the fitted
  reviewer effort and delay scales (``simulator.replay.fit``). It is fitted offline and
  stored with its source releases, date and validation result.
* **Starting state** (``current_state``): the release's open PRs as they are now, each at
  the review round it has reached, and the release's measured reviewers per week.
* **Run** (``compare``): baseline and scenario from the same starting state until the next
  milestone (Code Freeze, else release day, else ``DEFAULT_HORIZON_DAYS``). New PRs arrive
  at the measured rate. Each PR's random numbers are drawn per pool and replication, so a
  change to one pool leaves every other pool's numbers untouched (common random numbers).
* **Results** are ranges over replications (10th-90th percentile), never one number.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from engine.projection import World
from engine.review_rounds import review_rounds
from simulator.calibrate import Inputs, Path, PoolInputs, assign, days, window
from simulator.model import PoolSpec, PRResult, SimPR, simulate
from simulator.replay import staffing

DEFAULT_HORIZON_DAYS = 28.0
REPLICATIONS = 8
SEED = 20261122
MAX_REVIEWER_CHANGE = 50
MAX_ARRIVAL_MULTIPLIER = 3.0
TOTAL = "all"
_NO_PATH = Path(0, (), False, 0.0)


@dataclass(frozen=True)
class Calibration:
    """Measured and fitted inputs, with where they came from."""

    release_key: str  # the release it is used for
    inputs: Inputs
    effort_days: float
    scales: Mapping[str, tuple[float, float]]  # (first, later) delay scale per pool
    validation: Mapping[str, Any]  # summary of the newest validation run
    data_until: datetime

    @property
    def validated(self) -> bool:
        """Only true when the stored validation passed on every release."""
        return bool(self.validation.get("passed", False))


@dataclass(frozen=True)
class InFlight:
    """An open PR at the start of the run. Times in days from now (negative = past)."""

    key: str
    pool: str
    opened_at: float
    done_rounds: int
    previous_visible: float


@dataclass(frozen=True)
class State:
    """Where the release stands now."""

    release_key: str
    as_of: datetime
    horizon_at: datetime
    horizon_label: str  # "Code Freeze", "release day" or "4 weeks"
    in_flight: tuple[InFlight, ...]
    staffing: Mapping[str, float]  # measured reviewers per week per pool

    @property
    def horizon_days(self) -> float:
        """Length of the run."""
        return max(days(self.horizon_at - self.as_of), 1.0)


def horizon(world: World, release_key: str) -> tuple[datetime, str]:
    """The next milestone after now."""
    r = world.releases[release_key]
    if r.code_freeze_at is not None and r.code_freeze_at > world.as_of:
        return r.code_freeze_at, "Code Freeze"
    if r.release_at is not None and r.release_at > world.as_of:
        return r.release_at, "release day"
    return world.as_of + timedelta(days=DEFAULT_HORIZON_DAYS), "4 weeks"


def current_state(world: World, release_key: str, pools: Sequence[str]) -> State:
    """Open PRs of the release cycle, each at the review round it has reached."""
    r = world.releases[release_key]
    if r.cycle_start_at is None:
        raise ValueError(f"{release_key} has no cycle start date")
    now = world.as_of
    in_flight = []
    for pr in sorted(world.pull_requests.values(), key=lambda p: (p.created_at, p.key)):
        if not pr.is_open or not r.cycle_start_at <= pr.created_at <= now:
            continue
        rounds = [x for x in review_rounds(pr) if x.started_at <= now]
        last = max((x.ended_at for x in rounds), default=pr.created_at)
        in_flight.append(
            InFlight(
                key=pr.key,
                pool=assign(pr, pools),
                opened_at=days(pr.created_at - now),
                done_rounds=len(rounds),
                previous_visible=days(min(last, now) - now),
            )
        )
    at, label = horizon(world, release_key)
    try:
        staff = staffing(world, window(world, release_key), list(pools))
    except ValueError:
        staff = {}
    return State(release_key, now, at, label, tuple(in_flight), staff)


@dataclass(frozen=True)
class PoolChange:
    """A change to one pool. Every field defaults to "no change"."""

    reviewers: int = 0  # experienced reviewers added (negative = removed)
    new_reviewers: int = 0  # who start slow and ramp up
    ramp_weeks: float = 0.0
    interruption: float = 0.0  # share of reviewer time lost, 0..0.9


@dataclass(frozen=True)
class Scenario:
    """A named what-if."""

    name: str = "baseline"
    pools: Mapping[str, PoolChange] = field(default_factory=dict)
    arrival_multiplier: float = 1.0

    def problems(self, known_pools: Sequence[str]) -> list[str]:
        """Why this scenario cannot run (empty when it can)."""
        out = [f"unknown pool {p}" for p in self.pools if p not in known_pools]
        if not 0 <= self.arrival_multiplier <= MAX_ARRIVAL_MULTIPLIER:
            out.append(f"arrival multiplier must be 0..{MAX_ARRIVAL_MULTIPLIER}")
        for name, c in self.pools.items():
            if abs(c.reviewers) > MAX_REVIEWER_CHANGE or not 0 <= c.new_reviewers <= 50:
                out.append(f"{name}: reviewer change out of range")
            if not 0 <= c.interruption <= 0.9:
                out.append(f"{name}: interruption must be 0..0.9")
            if not 0 <= c.ramp_weeks <= 52:
                out.append(f"{name}: ramp-up must be 0..52 weeks")
        return out


def base_reviewers(staff: Mapping[str, float], pool: str) -> int:
    """Measured reviewers per week, rounded, at least one (as in the replay)."""
    return max(1, round(staff.get(pool, 0.0)))


def pool_specs(cal: Calibration, state: State, scenario: Scenario) -> dict[str, PoolSpec]:
    """Staffing and speed of every pool under ``scenario``."""
    out = {}
    for pool in cal.inputs.pools:
        change = scenario.pools.get(pool, PoolChange())
        first, later = cal.scales[pool]
        out[pool] = PoolSpec(
            reviewers=max(0, base_reviewers(state.staffing, pool) + change.reviewers),
            effort_days=cal.effort_days,
            first_scale=first,
            follow_scale=later,
            interruption=change.interruption,
            new_reviewers=change.new_reviewers,
            ramp_weeks=change.ramp_weeks,
        )
    return out


def _pick(paths: Sequence[Path], rng: np.random.Generator, at_least: int) -> Path:
    """A real path that has at least ``at_least`` rounds (an open PR is past those)."""
    fits = [p for p in paths if p.rounds >= at_least] or list(paths)
    return fits[int(rng.integers(len(fits)))] if fits else _NO_PATH


def _arrival_times(rng: np.random.Generator, per_day: float, until: float) -> list[float]:
    """Poisson arrivals. Gaps are unit draws scaled by the rate, so a higher rate keeps
    the same random numbers and only packs arrivals closer together."""
    if per_day <= 0:
        return []
    out: list[float] = []
    t = 0.0
    while True:
        t += float(rng.exponential(1.0)) / per_day
        if t >= until:
            return out
        out.append(t)


def _prs_for_pool(
    pool: PoolInputs,
    pool_index: int,
    in_flight: Sequence[InFlight],
    until: float,
    multiplier: float,
    rep: int,
    seed: int,
) -> tuple[list[SimPR], list[np.ndarray[Any, Any]]]:
    paths_rng = np.random.default_rng([seed, rep, pool_index, 0])
    arrive_rng = np.random.default_rng([seed, rep, pool_index, 1])
    effort_rng = np.random.default_rng([seed, rep, pool_index, 2])
    prs: list[SimPR] = []
    for pr in in_flight:
        path = _pick(pool.paths, paths_rng, pr.done_rounds)
        # In-flight PRs keep their real history; a path ending where they are now means
        # only the final delay is left.
        prs.append(
            SimPR(
                pr.key,
                pool.name,
                path,
                opened_at=pr.opened_at,
                done_rounds=min(pr.done_rounds, path.rounds),
                previous_visible=pr.previous_visible,
            )
        )
    per_day = pool.arrivals_per_week * multiplier / 7
    for i, at in enumerate(_arrival_times(arrive_rng, per_day, until)):
        prs.append(SimPR(f"new:{pool.name}:{i}", pool.name, _pick(pool.paths, paths_rng, 0), at))
    draws = [effort_rng.exponential(1.0, size=max(p.path.rounds, 0)) for p in prs]
    return prs, draws


@dataclass(frozen=True)
class Range:
    """Median and 10th-90th percentile over replications."""

    median: float
    low: float
    high: float


def _range(xs: Sequence[float]) -> Range | None:
    if not xs:
        return None
    return Range(
        round(float(np.median(xs)), 3),
        round(float(np.percentile(xs, 10)), 3),
        round(float(np.percentile(xs, 90)), 3),
    )


@dataclass(frozen=True)
class PoolOutcome:
    """One pool (or ``all``) at the horizon."""

    pool: str
    reviewers: int | None  # experienced + new; None for the total
    review_wait_days: Range | None  # median wait before a review round, from now on
    merged: Range | None  # PRs merged by the horizon
    not_merged: Range | None  # open now or arriving, not merged by the horizon


@dataclass(frozen=True)
class Outcome:
    """Every pool and the total, for one scenario."""

    scenario: Scenario
    pools: tuple[PoolOutcome, ...]
    total: PoolOutcome


def _summarize(
    runs: Sequence[Sequence[PRResult]], pools: Sequence[str], specs: Mapping[str, PoolSpec]
) -> tuple[tuple[PoolOutcome, ...], PoolOutcome]:
    def outcome(name: str, keep: set[str] | None) -> PoolOutcome:
        waits, merged, open_ = [], [], []
        for results in runs:
            rs = [r for r in results if keep is None or r.pool in keep]
            ws = [w for r in rs for at, w in r.round_waits if at > 0]
            if ws:
                waits.append(statistics.median(ws))
            merged.append(float(sum(r.merged_at is not None for r in rs)))
            open_.append(float(sum(r.merged_at is None for r in rs)))
        spec = specs.get(name)
        return PoolOutcome(
            name,
            spec.capacity if spec else None,
            _range(waits),
            _range(merged),
            _range(open_),
        )

    return tuple(outcome(p, {p}) for p in pools), outcome(TOTAL, None)


def run(
    cal: Calibration,
    state: State,
    scenario: Scenario,
    replications: int = REPLICATIONS,
    seed: int = SEED,
) -> Outcome:
    """Simulate ``scenario`` from the current state until the horizon."""
    pools = list(cal.inputs.pools)
    specs = pool_specs(cal, state, scenario)
    by_pool: dict[str, list[InFlight]] = {p: [] for p in pools}
    for pr in state.in_flight:
        by_pool.setdefault(pr.pool, []).append(pr)
    until = state.horizon_days
    runs = []
    for rep in range(replications):
        prs: list[SimPR] = []
        draws: list[np.ndarray[Any, Any]] = []
        for i, pool in enumerate(pools):
            p, d = _prs_for_pool(
                cal.inputs.pools[pool],
                i,
                by_pool[pool],
                until,
                scenario.arrival_multiplier,
                rep,
                seed,
            )
            prs.extend(p)
            draws.extend(d)
        runs.append(simulate(prs, specs, until=until, seed=seed + rep, effort_draws=draws))
    pool_out, total = _summarize(runs, pools, specs)
    return Outcome(scenario, pool_out, total)


@dataclass(frozen=True)
class Comparison:
    """Baseline next to a scenario (CLAUDE.md §14)."""

    baseline: Outcome
    scenario: Outcome
    replications: int
    seed: int


def compare(
    cal: Calibration,
    state: State,
    scenario: Scenario,
    replications: int = REPLICATIONS,
    seed: int = SEED,
    baseline: Outcome | None = None,
) -> Comparison:
    """Run the baseline (unless given, e.g. from a cache) and the scenario."""
    base = baseline or run(cal, state, Scenario(), replications, seed)
    return Comparison(base, run(cal, state, scenario, replications, seed), replications, seed)


# ---- (de)serialisation of a calibration, for storage -------------------------------------


def calibration_to_json(cal: Calibration) -> dict[str, Any]:
    """Plain JSON (paths included, so a stored calibration is self-contained)."""
    return {
        "release_key": cal.release_key,
        "source_releases": list(cal.inputs.source_releases),
        "measured_at": cal.inputs.measured_at.isoformat(),
        "data_until": cal.data_until.isoformat(),
        "effort_days": cal.effort_days,
        "scales": {k: list(v) for k, v in cal.scales.items()},
        "validation": dict(cal.validation),
        "pools": {
            name: {
                "prs": p.prs,
                "reviewers_per_week": p.reviewers_per_week,
                "arrivals_per_week": p.arrivals_per_week,
                "first_wait_median_days": p.first_wait_median_days,
                "follow_wait_median_days": p.follow_wait_median_days,
                "paths": [[x.rounds, list(x.waits_days), x.merges, x.final_days] for x in p.paths],
            }
            for name, p in cal.inputs.pools.items()
        },
    }


def calibration_from_json(data: Mapping[str, Any]) -> Calibration:
    """Inverse of ``calibration_to_json``."""
    pools = {
        name: PoolInputs(
            name=name,
            prs=p["prs"],
            reviewers_per_week=p["reviewers_per_week"],
            arrivals_per_week=p["arrivals_per_week"],
            first_wait_median_days=p["first_wait_median_days"],
            follow_wait_median_days=p["follow_wait_median_days"],
            paths=tuple(Path(r, tuple(w), m, f) for r, w, m, f in p["paths"]),
        )
        for name, p in data["pools"].items()
    }
    return Calibration(
        release_key=data["release_key"],
        inputs=Inputs(
            tuple(data["source_releases"]), datetime.fromisoformat(data["measured_at"]), pools
        ),
        effort_days=data["effort_days"],
        scales={k: (v[0], v[1]) for k, v in data["scales"].items()},
        validation=data["validation"],
        data_until=datetime.fromisoformat(data["data_until"]),
    )


def scenario_to_json(s: Scenario) -> dict[str, Any]:
    """Settings of a scenario as plain JSON."""
    return {
        "name": s.name,
        "arrival_multiplier": s.arrival_multiplier,
        "pools": {k: asdict(v) for k, v in sorted(s.pools.items())},
    }


def scenario_from_json(data: Mapping[str, Any]) -> Scenario:
    """Inverse of ``scenario_to_json``."""
    return Scenario(
        name=data.get("name", "baseline"),
        pools={k: PoolChange(**v) for k, v in data.get("pools", {}).items()},
        arrival_multiplier=data.get("arrival_multiplier", 1.0),
    )


def comparison_to_json(c: Comparison) -> dict[str, Any]:
    """Baseline and scenario results as plain JSON."""

    def outcome(o: Outcome) -> dict[str, Any]:
        return {
            "scenario": scenario_to_json(o.scenario),
            "pools": [asdict(p) for p in o.pools],
            "total": asdict(o.total),
        }

    return {
        "baseline": outcome(c.baseline),
        "scenario": outcome(c.scenario),
        "replications": c.replications,
        "seed": c.seed,
    }
