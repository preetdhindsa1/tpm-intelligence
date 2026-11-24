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

import hashlib
import json
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
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
    # M7 step 4: merge times of main PRs only (inf = never merged), and features removed
    # although their required code merged by Code Freeze, per stage ("" = unknown).
    main_durations_days: tuple[float, ...] = ()
    removed_despite_code: Mapping[str, Rate] = field(default_factory=dict)

    @property
    def has_history(self) -> bool:
        """True if earlier releases gave at least one measured PR duration to draw from.

        A source release alone is not enough: Kafka 4.5.0 calibrates on 4.4.0 but had no
        linked PR durations (2026-11-23).
        """
        return bool(self.source_releases) and bool(self.durations_days)

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
            "main_pr_samples": len(self.main_durations_days),
            "removed_despite_code_rate": {
                (k or "unknown"): {"rate": round(r.mean, 3), "k": r.k, "n": r.n}
                for k, r in sorted(self.removed_despite_code.items())
            },
        }


def calibrate(world: World, release_keys: Sequence[str]) -> Calibration:
    """Measure durations, new-PR rates and landing rates on finished releases."""
    return calibrate_tracked(world, release_keys)[0]


def calibrate_tracked(
    world: World, release_keys: Sequence[str]
) -> tuple[Calibration, frozenset[str]]:
    """:func:`calibrate`, plus the subjects it read (P3-M4 calibration cache).

    The subjects are the release keys, every feature that was ever in them and every PR
    with a verified link to one of those features. A new event on any of them can change
    the calibration; an event elsewhere cannot, except a brand-new PR that links to an
    old feature (ADR-0019 covers that with a time limit).
    """
    read: set[str] = set(release_keys)
    durations: list[float] = []
    main_durations: list[float] = []
    new_pr: dict[tuple[int, bool], list[int]] = {}
    landing: dict[int, list[int]] = {}
    removed: dict[str, list[int]] = {}
    for key in release_keys:
        release = world.releases[key]
        freeze = release.code_freeze_at
        if freeze is None or release.cycle_start_at is None:
            continue
        links = link_release(world, key)
        features = world.features_ever_in(key)
        read.update(f.key for f in features)
        read.update(links.linked_pr_keys())
        seen_prs: set[str] = set()
        seen_main: set[str] = set()
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
            in_cycle = [pr for pr in prs if release.cycle_start_at <= pr.created_at <= freeze]
            main = main_pr([pr.key for pr in in_cycle if pr.state != "closed"], world, links, f.key)
            if main is not None and main.key not in seen_main:
                seen_main.add(main.key)
                main_durations.append(
                    _days(main.merged_at - main.created_at) if main.merged_at else float("inf")
                )
            if (
                main is not None
                and outcome is not None
                and main.merged_at is not None
                and main.merged_at <= freeze
                and key in releases_at(f, freeze)
            ):
                # In the release at freeze with its main PR merged: did it still go?
                stage = f.stage or ""
                removed.setdefault(stage, [0, 0])
                removed[stage][0] += int(not outcome)
                removed[stage][1] += 1
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
    calibration = Calibration(
        source_releases=tuple(release_keys),
        as_of=world.as_of,
        durations_days=tuple(sorted(durations)),
        new_pr={k: Rate(*v) for k, v in new_pr.items()},
        landing={k: Rate(*v) for k, v in landing.items()},
        main_durations_days=tuple(sorted(main_durations)),
        removed_despite_code={k: Rate(*v) for k, v in removed.items()},
    )
    return calibration, frozenset(read)


def finished_releases(world: World, before: datetime, exclude: str) -> list[str]:
    """Releases of ``exclude``'s project released before ``before`` (calibration may only
    use these). Projects never calibrate each other: Kafka and Kubernetes differ in
    process, cadence and review culture (ADR-0018)."""
    project = exclude.split(":", 1)[0]
    return sorted(
        k
        for k, r in world.releases.items()
        if k != exclude
        and k.split(":", 1)[0] == project
        and r.release_at is not None
        and r.release_at <= before
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
    # M7 step 4 variants (ADR-0005): which PRs' merge times feed the residual draws, and
    # whether features can be removed for non-code reasons after their code merged.
    # "main" adopted 2026-11-22 (lower Brier in 9 of 12 odds cases and CRPS in 8 of 12
    # merge-date cases; in-sample). Non-code removal rejected (worse Brier in 9 of 12).
    durations: Literal["all", "main"] = "main"
    non_code_removal: bool = False


DEFAULT_FORECAST = ForecastConfig()

# Name of the forecast model. Bump it whenever the model's code changes what it outputs
# (ADR-0015): snapshots only count as a test of the version that made them.
MODEL_NAME = "forecast-m7.1"


def model_version(config: ForecastConfig = DEFAULT_FORECAST) -> str:
    """``MODEL_NAME`` plus a short hash of every setting that changes the output."""
    settings = json.dumps(asdict(config), sort_keys=True)
    return f"{MODEL_NAME}+{hashlib.sha256(settings.encode()).hexdigest()[:8]}"


INSUFFICIENT_HISTORY = "insufficient_history"  # no earlier release to calibrate on


@dataclass(frozen=True)
class Forecast:
    """Odds for one feature with its range and the inputs used."""

    feature_key: str
    as_of: datetime
    status: str  # "forecast" | "after_freeze" | "no_freeze_date" | "insufficient_history"
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


@dataclass(frozen=True)
class CompletionDraws:
    """Simulated completion times, per bootstrap replication, in days after ``as_of``.

    ``total[r][i]`` is when the feature's required work (main PR, its stated
    prerequisites, and a new PR if one is needed) has all merged in draw ``i`` of
    replication ``r``; ``inf`` = never. ``per_pr[r]`` holds each open PR's own time.
    """

    open_prs: tuple[str, ...]
    per_pr: tuple[Array, ...]
    total: tuple[Array, ...]
    new_pr_rate: Rate


def simulate_completion(
    feature: Feature,
    world: World,
    links: ReleaseLinks,
    calibration: Calibration,
    days_to_freeze: float,
    new_work_window_days: float,
    config: ForecastConfig = DEFAULT_FORECAST,
    skip_closed_main: bool = False,
) -> CompletionDraws:
    """The Monte Carlo of ADR-0005, keeping each draw's completion time.

    A needed new PR opens uniformly within ``new_work_window_days`` (Code Freeze before
    it, release day after it). The new-PR rate comes from the days-to-freeze bucket.

    ``skip_closed_main`` (merge dates): a PR closed without merging cannot deliver the
    code, so the main PR is chosen among the others, and if every PR was closed a new
    one is needed. Off for the odds, whose backtested model treats a closed main PR as
    nothing left to merge (ADR-0005).
    """
    t = world.as_of
    prs = [
        world.pull_requests[k] for k in links.verified_prs(feature.key) if k in world.pull_requests
    ]
    open_prs = sorted((p for p in prs if p.is_open), key=lambda p: p.key)
    has_prs = bool(prs)
    force_new = False
    if skip_closed_main:
        live = [p.key for p in prs if p.state != "closed"]
        main = main_pr(live, world, links, feature.key)
        force_new = has_prs and main is None
    else:
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
    rate = calibration.new_pr.get((bucket(max(days_to_freeze, 0.0)), has_prs), Rate(0, 0))
    source = (
        calibration.main_durations_days
        if config.durations == "main" and calibration.main_durations_days
        else calibration.durations_days
    )
    pool = np.asarray(source, dtype=np.float64)
    if pool.size == 0:
        pool = np.array([np.inf])
    keys = [p.key for p in open_prs]
    deps = [
        (keys.index(d), i) for i, p in enumerate(open_prs) for d in pr_dependencies(p) if d in keys
    ]
    required = np.array([k in required_keys for k in keys], dtype=bool)

    rng = np.random.default_rng(_seed(config, feature.key))
    n = config.sims
    per_pr: list[Array] = []
    total: list[Array] = []
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
        needs_new = rng.random(n) < q
        if force_new:
            needs_new[:] = True  # every PR was closed without merging
        new_done = rng.random(n) * new_work_window_days + rng.choice(boot, size=n)
        blocking = done[required] if open_prs else done
        when = blocking.max(axis=0) if blocking.shape[0] else np.zeros(n)
        if new_work_possible:
            when = np.where(needs_new, np.maximum(when, new_done), when)
        if not has_prs:
            when = np.where(needs_new, when, np.inf)  # nothing exists yet: a PR must open
        per_pr.append(done)
        total.append(when)
    return CompletionDraws(tuple(keys), tuple(per_pr), tuple(total), rate)


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
    if not calibration.has_history:
        # Nothing measured to draw from: an uninformed prior would print "50%" that looks
        # like an estimate (issue #9). Say so instead.
        return Forecast(feature.key, t, INSUFFICIENT_HISTORY, None, None, None)
    horizon = _days(freeze - t)
    draws = simulate_completion(feature, world, links, calibration, horizon, horizon, config)
    probs = [float((when <= horizon).mean()) for when in draws.total]
    if config.non_code_removal:
        # A feature whose code is in can still be removed (docs, PRR, release team call):
        # measured per stage on earlier releases, drawn from its Beta posterior.
        rate = calibration.removed_despite_code.get(feature.stage or "") or Rate(0, 0)
        rng = np.random.default_rng(_seed(config, feature.key) ^ 0x5EED)
        keep = 1 - rng.beta(rate.k + 1, rate.n - rate.k + 1, size=len(probs))
        probs = [p * float(k) for p, k in zip(probs, keep, strict=True)]
    on_time = np.zeros(len(draws.open_prs))
    for done in draws.per_pr:
        if draws.open_prs:
            on_time += (done <= horizon).mean(axis=1)
    lo, hi = np.percentile(probs, config.interval)
    return Forecast(
        feature_key=feature.key,
        as_of=t,
        status="forecast",
        probability=round(float(np.mean(probs)), 3),
        low=round(float(lo), 3),
        high=round(float(hi), 3),
        open_prs=draws.open_prs,
        pr_on_time={
            k: round(float(v / config.replications), 3)
            for k, v in zip(draws.open_prs, on_time, strict=True)
        },
        new_pr_needed=round(draws.new_pr_rate.mean, 3),
    )


def forecast_release(
    world: World,
    release_key: str,
    calibration: Calibration,
    config: ForecastConfig = DEFAULT_FORECAST,
    features: Iterable[Feature] | None = None,
    links: ReleaseLinks | None = None,
) -> list[Forecast]:
    """Forecast every feature currently in the release (or the given ones).

    ``links``: the release's linking if already computed (see ``assess_release``).
    """
    release = world.releases[release_key]
    links = links if links is not None else link_release(world, release_key)
    chosen = list(features) if features is not None else world.features_in(release_key)
    return [forecast_feature(f, release, world, links, calibration, config) for f in chosen]
