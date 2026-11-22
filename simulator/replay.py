"""Replay a release, fit reviewer time per round, and validate (ADR-0012). Pure, no I/O.

**Replay**: the release's real PRs arrive at their real opening times and queue in their
pool. Each follows a path drawn from the *source* releases' paths for that pool. Staffing is
the replayed release's own measured reviewers per week ("its real staffing", CLAUDE.md §14).

**Fit**: per pool, bisect the work scale for first and later rounds (``simulator.model``) so
that
the simulated median waits before first and later rounds match the measured ones on the
*source* releases. The validated release is never used to fit.

**Validate**: replay a release that was *not* used to fit, and compare the simulated
medians with the real ones (observed until the same horizon):

* median wait before a review round (all rounds);
* median time to merge.

Both must be within ``TOLERANCE`` (±20%) of the real value.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from engine.forecast import finished_releases
from engine.projection import World
from engine.review_rounds import review_rounds, review_waits
from simulator.calibrate import (
    Inputs,
    Path,
    Window,
    assign,
    days,
    measure,
    reviewer_weeks,
    window,
    window_prs,
)
from simulator.model import PoolSpec, PRResult, SimPR, simulate

TOLERANCE = 0.20
REPLICATIONS = 8
FIT_REPLICATIONS = 3
FIT_STEPS = 12
EFFORT_STEPS = 8
EFFORT_BOUNDS = (0.02, 2.0)  # days of reviewer time per round
DEFAULT_EFFORT = 0.1
SCALE_BOUNDS = (0.01, 2.0)  # share of the real wait that is work, not queue
SEED = 20261122


@dataclass(frozen=True)
class Metrics:
    """The two validation measures, in days."""

    review_wait_median: float | None
    time_to_merge_median: float | None
    rounds: int
    merged: int


def _median(xs: Sequence[float]) -> float | None:
    return round(statistics.median(xs), 3) if xs else None


def real_metrics(world: World, w: Window) -> Metrics:
    """Measured on the real PRs of the window, observed until its horizon."""
    waits: list[float] = []
    ttm: list[float] = []
    for pr in window_prs(world, w):
        rounds = [r for r in review_rounds(pr) if r.started_at < w.horizon]
        waits.extend(days(x) for x in review_waits(pr, rounds))
        if pr.merged_at is not None and pr.merged_at <= w.horizon:
            ttm.append(days(pr.merged_at - pr.created_at))
    return Metrics(_median(waits), _median(ttm), len(waits), len(ttm))


def sim_metrics(results: Sequence[PRResult], horizon: float) -> Metrics:
    """The same measures on simulated PRs (all opened at or after time 0)."""
    waits = [w for r in results for at, w in r.round_waits if at <= horizon]
    ttm = [r.merged_at - r.opened_at for r in results if r.merged_at is not None]
    return Metrics(_median(waits), _median(ttm), len(waits), len(ttm))


def staffing(world: World, w: Window, pools: Sequence[str]) -> dict[str, float]:
    """Median reviewers per week per pool in this release (fractional)."""
    prs = window_prs(world, w)
    weeks = reviewer_weeks(prs, w, {p.key: assign(p, pools) for p in prs})
    return {pool: statistics.median(weeks[pool]) if pool in weeks else 0.0 for pool in pools}


def _arrivals(world: World, w: Window, inputs: Inputs, rng: np.random.Generator) -> list[SimPR]:
    pools = list(inputs.pools)
    out = []
    for pr in window_prs(world, w):
        pool = assign(pr, pools)
        paths = inputs.pools[pool].paths
        path = paths[int(rng.integers(len(paths)))] if paths else Path(0, (), False, 0.0)
        out.append(SimPR(pr.key, pool, path, opened_at=days(pr.created_at - w.start)))
    return out


def replay(
    world: World,
    w: Window,
    inputs: Inputs,
    service: Mapping[str, tuple[float, float]],
    staff: Mapping[str, float],
    seed: int,
    effort_days: float | None = None,
) -> list[PRResult]:
    """One replay of the window (see module docstring)."""
    rng = np.random.default_rng(seed)
    prs = _arrivals(world, w, inputs, rng)
    specs = {
        pool: PoolSpec(
            reviewers=max(1, round(staff.get(pool, 0.0))),
            effort_days=DEFAULT_EFFORT if effort_days is None else effort_days,
            first_scale=service[pool][0],
            follow_scale=service[pool][1],
        )
        for pool in inputs.pools
    }
    return simulate(prs, specs, until=days(w.horizon - w.start), seed=seed + 1)


def _waits(results: Sequence[PRResult]) -> dict[tuple[str, int], list[float]]:
    """Simulated waits per (pool, 0 = first round / 1 = later rounds)."""
    out: dict[tuple[str, int], list[float]] = {}
    for r in results:
        for i, (_, wait) in enumerate(r.round_waits):
            out.setdefault((r.pool, min(i, 1)), []).append(wait)
    return out


def fit_service(
    world: World,
    inputs: Inputs,
    effort_days: float,
    windows: Sequence[Window],
    staff: Mapping[str, Mapping[str, float]],
) -> dict[str, tuple[float, float]]:
    """(first, later) delay scale per pool for a given effort, fitted on the source releases."""
    keys = [(p, kind) for p in inputs.pools for kind in (0, 1)]
    lo = dict.fromkeys(keys, float(np.log(SCALE_BOUNDS[0])))
    hi = dict.fromkeys(keys, float(np.log(SCALE_BOUNDS[1])))
    targets = {(p, 0): pi.first_wait_median_days for p, pi in inputs.pools.items()} | {
        (p, 1): pi.follow_wait_median_days for p, pi in inputs.pools.items()
    }
    for _ in range(FIT_STEPS):
        mid = {k: float(np.exp((lo[k] + hi[k]) / 2)) for k in keys}
        service = {p: (mid[(p, 0)], mid[(p, 1)]) for p in inputs.pools}
        sims: dict[tuple[str, int], list[float]] = {}
        for w in windows:
            for rep in range(FIT_REPLICATIONS):
                res = replay(
                    world, w, inputs, service, staff[w.release_key], SEED + 97 * rep, effort_days
                )
                for k, ws in _waits(res).items():
                    sims.setdefault(k, []).extend(ws)
        for k in keys:
            target, got = targets[k], sims.get(k)
            if target is None or not got:
                continue
            if statistics.median(got) > target:
                hi[k] = float(np.log(mid[k]))
            else:
                lo[k] = float(np.log(mid[k]))
    return {
        p: (
            round(float(np.exp((lo[(p, 0)] + hi[(p, 0)]) / 2)), 4),
            round(float(np.exp((lo[(p, 1)] + hi[(p, 1)]) / 2)), 4),
        )
        for p in inputs.pools
    }


@dataclass(frozen=True)
class Fit:
    """Fitted parameters and how well they follow the source releases."""

    effort_days: float
    scales: Mapping[str, tuple[float, float]]
    loss: float  # squared log error of per-release median review wait


def fit(world: World, inputs: Inputs) -> Fit:
    """Fit reviewer effort and delay scales on the source releases only.

    * For each candidate effort (a log-spaced grid), the per-pool delay scales are fitted
      so that pooled median waits match (``fit_service``).
    * The effort kept is the one whose simulated median review wait best follows the
      real one **release by release** (least squared log error). Source releases differ in
      load and staffing, so this is the information that says how much reviewer capacity
      matters.
    """
    windows = [window(world, k) for k in inputs.source_releases]
    staff = {w.release_key: staffing(world, w, list(inputs.pools)) for w in windows}
    real = {w.release_key: real_metrics(world, w).review_wait_median for w in windows}
    best: tuple[float, float, dict[str, tuple[float, float]]] | None = None
    for effort in np.geomspace(*EFFORT_BOUNDS, EFFORT_STEPS):
        scales = fit_service(world, inputs, float(effort), windows, staff)
        loss = 0.0
        for w in windows:
            sims = [
                sim_metrics(
                    replay(
                        world,
                        w,
                        inputs,
                        scales,
                        staff[w.release_key],
                        SEED + 7 * rep,
                        float(effort),
                    ),
                    days(w.horizon - w.start),
                ).review_wait_median
                for rep in range(FIT_REPLICATIONS)
            ]
            got = [x for x in sims if x]
            target = real[w.release_key]
            if got and target:
                loss += float(np.log(statistics.median(got) / target)) ** 2
        if best is None or loss < best[0]:
            best = (loss, float(effort), scales)
    assert best is not None  # noqa: S101 - EFFORT_STEPS > 0
    return Fit(round(best[1], 4), best[2], round(best[0], 4))


@dataclass(frozen=True)
class Check:
    """One measure compared with reality."""

    name: str
    real: float | None
    simulated: float | None
    simulated_low: float | None
    simulated_high: float | None

    @property
    def error(self) -> float | None:
        """Relative error of the simulated median."""
        if self.real in (None, 0) or self.simulated is None:
            return None
        return round((self.simulated - self.real) / self.real, 3)

    @property
    def passed(self) -> bool:
        """Within the tolerance."""
        return self.error is not None and abs(self.error) <= TOLERANCE


@dataclass(frozen=True)
class Validation:
    """Result of replaying one held-out release."""

    release_key: str
    source_releases: tuple[str, ...]
    service_days: Mapping[str, tuple[float, float]]
    effort_days: float
    staffing: Mapping[str, float]
    checks: tuple[Check, ...]
    replications: int

    @property
    def passed(self) -> bool:
        """Every check within tolerance."""
        return all(c.passed for c in self.checks)


def _spread(values: Sequence[float | None]) -> tuple[float | None, float | None, float | None]:
    xs = [v for v in values if v is not None]
    if not xs:
        return None, None, None
    return (
        round(float(np.median(xs)), 3),
        round(float(np.percentile(xs, 10)), 3),
        round(float(np.percentile(xs, 90)), 3),
    )


def validate(world: World, release_key: str, replications: int = REPLICATIONS) -> Validation:
    """Fit on releases finished before ``release_key`` started, replay it, compare."""
    w = window(world, release_key)
    sources = finished_releases(world, w.start, exclude=release_key)
    if not sources:
        raise ValueError(f"no finished release before {release_key} to calibrate on")
    inputs = measure(world, sources)
    fitted = fit(world, inputs)
    service = fitted.scales
    staff = staffing(world, w, list(inputs.pools))
    real = real_metrics(world, w)
    horizon = days(w.horizon - w.start)
    sims = [
        sim_metrics(
            replay(world, w, inputs, service, staff, SEED + 1000 + 31 * r, fitted.effort_days),
            horizon,
        )
        for r in range(replications)
    ]
    wait = _spread([s.review_wait_median for s in sims])
    ttm = _spread([s.time_to_merge_median for s in sims])
    return Validation(
        release_key=release_key,
        source_releases=tuple(sources),
        service_days=service,
        effort_days=fitted.effort_days,
        staffing={k: round(v, 2) for k, v in staff.items()},
        checks=(
            Check("median review wait (days)", real.review_wait_median, *wait),
            Check("median time to merge (days)", real.time_to_merge_median, *ttm),
        ),
        replications=replications,
    )
