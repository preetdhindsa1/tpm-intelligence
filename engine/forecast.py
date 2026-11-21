"""Monte Carlo forecast: odds that a feature lands by Code Freeze (ADR-0005). Pure, no I/O.

Model
-----
For a feature in release ``R`` at prediction time ``t`` (before ``R``'s Code Freeze ``F``):

1. **Open linked PRs.** Each open verified PR of age ``a`` gets a sampled remaining time
   to merge: draw a calibration PR that was still unmerged at age ``a`` and take its
   remaining time (empirical residual life). Calibration PRs closed without merging
   count as "never merges".
2. **Dependencies.** A PR cannot finish before a PR it says it depends on.
3. **Work not opened yet.** With probability ``q`` (measured on earlier releases for the
   same days-to-freeze bucket and "has PRs yet?" state), a new PR is needed. It opens at
   a uniform time in ``[t, F)`` and takes a sampled full time to merge.
4. **Lands** if every sampled completion is at or before ``F``. A feature with no PRs
   that draws no new PR cannot land.

Uncertainty: ``replications`` bootstrap resamples of the calibration (durations
resampled, ``q`` drawn from its Beta posterior), ``sims`` draws each. The result is the
mean and the 10th-90th percentile across replications. Seeds are fixed per feature.

Calibration uses only releases that finished before ``t`` and data as of ``t``.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

import numpy as np
import numpy.typing as npt

from engine.graph import pr_dependencies
from engine.links import ReleaseLinks, link_release
from engine.projection import Feature, ReleaseInfo, World
from engine.rules import main_pr

Array = npt.NDArray[np.float64]
DAY = 86400.0
# Days-to-freeze buckets: [0,7), [7,14), [14,28), [28,56), [56, inf)
BUCKET_EDGES: tuple[float, ...] = (7.0, 14.0, 28.0, 56.0)
BUCKET_SAMPLE_DAYS: tuple[float, ...] = (3.5, 10.5, 21.0, 42.0, 70.0)
LANDED_WINDOW = timedelta(days=3)  # "still in the release 3 days after Code Freeze"


def bucket(days_to_freeze: float) -> int:
    """Index of the days-to-freeze bucket."""
    return sum(1 for edge in BUCKET_EDGES if days_to_freeze >= edge)


def _days(delta: timedelta) -> float:
    return delta.total_seconds() / DAY


def releases_at(feature: Feature, when: datetime) -> frozenset[str]:
    """Release keys the feature was in at ``when`` (from its membership history)."""
    state: set[str] = set()
    for m in feature.membership:
        if m.at > when:
            break
        (state.add if m.added else state.discard)(m.release_key)
    return frozenset(state)


def landed(feature: Feature, release: ReleaseInfo) -> bool | None:
    """Outcome: still in the release ``LANDED_WINDOW`` after Code Freeze (None if unknown)."""
    if release.code_freeze_at is None:
        return None
    return release.key in releases_at(feature, release.code_freeze_at + LANDED_WINDOW)


# ---------------------------------------------------------------- calibration


@dataclass(frozen=True)
class Rate:
    """k successes out of n."""

    k: int
    n: int

    @property
    def mean(self) -> float:
        """Posterior mean under a uniform Beta(1, 1) prior."""
        return (self.k + 1) / (self.n + 2)


@dataclass(frozen=True)
class Calibration:
    """Measured inputs, with where they came from (CLAUDE.md section 14: visible assumptions)."""

    source_releases: tuple[str, ...]
    as_of: datetime
    durations_days: tuple[float, ...]  # inf = never merged
    new_pr: Mapping[tuple[int, bool], Rate]  # (bucket, has_prs) -> needed a new PR
    landing: Mapping[int, Rate]  # bucket -> landed (climatology baseline)

    def describe(self) -> dict[str, object]:
        """Summary for display and logs."""
        finite = [d for d in self.durations_days if d != float("inf")]
        return {
            "source_releases": list(self.source_releases),
            "measured_as_of": self.as_of.isoformat(),
            "pr_samples": len(self.durations_days),
            "pr_never_merged_share": round(1 - len(finite) / len(self.durations_days), 3)
            if self.durations_days
            else None,
            "median_days_to_merge": round(float(np.median(finite)), 1) if finite else None,
            "new_pr_rate": {
                f"{b}:{h}": round(r.mean, 3) for (b, h), r in sorted(self.new_pr.items())
            },
            "landing_rate": {str(b): round(r.mean, 3) for b, r in sorted(self.landing.items())},
        }


def calibrate(world: World, release_keys: Sequence[str]) -> Calibration:
    """Measure durations, new-PR rates and landing rates on finished releases."""
    durations: list[float] = []
    new_pr: dict[tuple[int, bool], list[int]] = {}
    landing: dict[int, list[int]] = {}
    for key in release_keys:
        release = world.releases[key]
        freeze = release.code_freeze_at
        if freeze is None or release.cycle_start_at is None:
            continue
        links = link_release(world, key)
        features = world.features_ever_in(key)
        seen_prs: set[str] = set()
        for f in features:
            prs = [
                world.pull_requests[k]
                for k in links.verified_prs(f.key)
                if k in world.pull_requests
            ]
            for pr in prs:
                if pr.key in seen_prs or not (release.cycle_start_at <= pr.created_at <= freeze):
                    continue
                seen_prs.add(pr.key)
                durations.append(
                    _days(pr.merged_at - pr.created_at) if pr.merged_at else float("inf")
                )
            outcome = landed(f, release)
            for b, days in enumerate(BUCKET_SAMPLE_DAYS):
                t = freeze - timedelta(days=days)
                if key not in releases_at(f, t) or outcome is None:
                    continue
                has_prs = any(pr.created_at < t for pr in prs)
                got_new = any(t <= pr.created_at < freeze for pr in prs)
                new_pr.setdefault((b, has_prs), [0, 0])
                new_pr[(b, has_prs)][0] += int(got_new)
                new_pr[(b, has_prs)][1] += 1
                landing.setdefault(b, [0, 0])
                landing[b][0] += int(outcome)
                landing[b][1] += 1
    return Calibration(
        source_releases=tuple(release_keys),
        as_of=world.as_of,
        durations_days=tuple(sorted(durations)),
        new_pr={k: Rate(*v) for k, v in new_pr.items()},
        landing={k: Rate(*v) for k, v in landing.items()},
    )


def finished_releases(world: World, before: datetime, exclude: str) -> list[str]:
    """Releases released before ``before`` (calibration may only use these)."""
    return sorted(
        k
        for k, r in world.releases.items()
        if k != exclude and r.release_at is not None and r.release_at <= before
    )


# ---------------------------------------------------------------- simulation


@dataclass(frozen=True)
class ForecastConfig:
    """Simulation size. Interactive use keeps these small; backtests may raise them."""

    replications: int = 20
    sims: int = 500
    seed: int = 1338
    interval: tuple[float, float] = (10.0, 90.0)
    # Which open PRs must merge by Code Freeze: only the main (implementation) PR, or all
    # linked PRs. "all" failed its backtest (2026-11-21): 36-51% of features that landed
    # still had linked PRs open at freeze (ADR-0005).
    required_prs: Literal["main", "all"] = "main"


DEFAULT_FORECAST = ForecastConfig()


@dataclass(frozen=True)
class Forecast:
    """Odds for one feature with its range and the inputs used."""

    feature_key: str
    as_of: datetime
    status: str  # "forecast" | "after_freeze" | "no_freeze_date"
    probability: float | None
    low: float | None
    high: float | None
    open_prs: tuple[str, ...] = ()
    pr_on_time: Mapping[str, float] = field(default_factory=dict)
    new_pr_needed: float | None = None
    raw_probability: float | None = None  # before recalibration (engine/recalibrate.py)


def _seed(config: ForecastConfig, key: str) -> int:
    return config.seed ^ zlib.crc32(key.encode())


def _residuals(rng: np.random.Generator, pool: Array, age: float, n: int) -> Array:
    survivors = pool[pool > age]
    if survivors.size == 0:  # older than every calibration PR that eventually merged or not
        return np.full(n, np.inf)
    return rng.choice(survivors, size=n) - age


def forecast_feature(
    feature: Feature,
    release: ReleaseInfo,
    world: World,
    links: ReleaseLinks,
    calibration: Calibration,
    config: ForecastConfig = DEFAULT_FORECAST,
) -> Forecast:
    """Monte Carlo odds that ``feature`` lands by ``release``'s Code Freeze."""
    t, freeze = world.as_of, release.code_freeze_at
    if freeze is None:
        return Forecast(feature.key, t, "no_freeze_date", None, None, None)
    if t >= freeze:
        return Forecast(feature.key, t, "after_freeze", None, None, None)
    horizon = _days(freeze - t)
    prs = [
        world.pull_requests[k] for k in links.verified_prs(feature.key) if k in world.pull_requests
    ]
    open_prs = sorted((p for p in prs if p.is_open), key=lambda p: p.key)
    has_prs = bool(prs)
    main = main_pr([p.key for p in prs], world, links, feature.key)
    if config.required_prs == "main":
        # Only the main PR (plus anything it depends on) blocks; others are reported only.
        required_keys = {main.key} if main is not None and main.is_open else set()
        frontier = list(required_keys)
        while frontier:
            for dep in pr_dependencies(world.pull_requests[frontier.pop()]):
                if (
                    dep in world.pull_requests
                    and world.pull_requests[dep].is_open
                    and dep not in required_keys
                ):
                    required_keys.add(dep)
                    frontier.append(dep)
    else:
        required_keys = {p.key for p in open_prs}
    new_work_possible = config.required_prs == "all" or main is None
    rate = calibration.new_pr.get((bucket(horizon), has_prs), Rate(0, 0))
    pool = np.asarray(calibration.durations_days, dtype=np.float64)
    if pool.size == 0:
        pool = np.array([np.inf])
    keys = [p.key for p in open_prs]
    deps = [
        (keys.index(d), i) for i, p in enumerate(open_prs) for d in pr_dependencies(p) if d in keys
    ]

    rng = np.random.default_rng(_seed(config, feature.key))
    n = config.sims
    probs: list[float] = []
    on_time = np.zeros(len(open_prs))
    for _ in range(config.replications):
        boot = rng.choice(pool, size=pool.size)
        q = rng.beta(rate.k + 1, rate.n - rate.k + 1)
        done = (
            np.stack([_residuals(rng, boot, _days(t - p.created_at), n) for p in open_prs])
            if open_prs
            else np.zeros((0, n))
        )
        for _ in range(len(deps)):  # propagate along chains (at most len(deps) hops)
            for parent, child in deps:
                done[child] = np.maximum(done[child], done[parent])
        on_time += (done <= horizon).mean(axis=1) if open_prs else 0.0
        needs_new = rng.random(n) < q
        new_done = rng.random(n) * horizon + rng.choice(boot, size=n)
        required = np.array([k in required_keys for k in keys], dtype=bool)
        blocking = done[required] if open_prs else done
        ok = (blocking <= horizon).all(axis=0)
        if new_work_possible:
            ok &= ~needs_new | (new_done <= horizon)
        if not has_prs:
            ok &= needs_new  # nothing exists yet: a PR must be opened
        probs.append(float(ok.mean()))
    lo, hi = np.percentile(probs, config.interval)
    return Forecast(
        feature_key=feature.key,
        as_of=t,
        status="forecast",
        probability=round(float(np.mean(probs)), 3),
        low=round(float(lo), 3),
        high=round(float(hi), 3),
        open_prs=tuple(keys),
        pr_on_time={
            k: round(float(v / config.replications), 3) for k, v in zip(keys, on_time, strict=True)
        },
        new_pr_needed=round(rate.mean, 3),
    )


def forecast_release(
    world: World,
    release_key: str,
    calibration: Calibration,
    config: ForecastConfig = DEFAULT_FORECAST,
    features: Iterable[Feature] | None = None,
) -> list[Forecast]:
    """Forecast every feature currently in the release (or the given ones)."""
    release = world.releases[release_key]
    links = link_release(world, release_key)
    chosen = list(features) if features is not None else world.features_in(release_key)
    return [forecast_feature(f, release, world, links, calibration, config) for f in chosen]
