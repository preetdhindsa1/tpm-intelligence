"""Backtest of merge-date forecasts (engine/merge_date.py; ADR-0005 "Merge dates"). Pure.

At each lead time (days before Code Freeze; negative = after it), forecast every feature
in the release from data before that time, then compare with the day its main PR and
stated prerequisites actually merged.

Scores: coverage of the 10th-90th percentile range (target about 80%) and CRPS on whole
days, against a baseline built from earlier releases' features at the same point. The
validation rule was fixed in ADR-0005 before the first run.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from engine.forecast import DEFAULT_FORECAST, ForecastConfig, calibrate, finished_releases
from engine.links import ReleaseLinks, link_release
from engine.merge_date import (
    TAIL,
    MergeDateForecast,
    forecast_release_dates,
    grid,
    release_curve,
    required_done_at,
)
from engine.projection import ReleaseInfo, World, project
from pipeline.events import NormalizedEvent

DAY = 86400.0
COVERAGE_RANGE = (0.70, 0.90)


@dataclass(frozen=True)
class DateCase:
    """One feature's forecast and its actual merge day (inf = beyond the horizon)."""

    feature_key: str
    p10: float | None
    p50: float | None
    p90: float | None
    actual: float
    covered: bool
    crps: float
    crps_baseline: float


@dataclass(frozen=True)
class DateLeadResult:
    """Scores at one lead time."""

    release: str
    lead_days: int
    as_of: str
    calibration_releases: tuple[str, ...]
    baseline_samples: int
    n: int
    merged_within_horizon: float | None
    coverage: float | None
    crps: float | None
    crps_baseline: float | None
    skill: float | None
    passes: bool
    # Release curve check: features with required code merged by release day.
    count_at_release_forecast: tuple[float, float, float] | None  # mean, low, high
    count_at_release_actual: int | None
    cases: tuple[DateCase, ...]


def _rel(when: datetime, freeze: datetime) -> float:
    return (when - freeze).total_seconds() / DAY


_LINKS: dict[tuple[int, str], tuple[World, ReleaseLinks]] = {}


def _links(world: World, release_key: str) -> ReleaseLinks:
    """``link_release`` memoised per world object (it is the slow part of scoring)."""
    key = (id(world), release_key)
    hit = _LINKS.get(key)
    if hit is None or hit[0] is not world:
        if len(_LINKS) > 8:  # worlds are large: keep only a few
            _LINKS.clear()
        hit = (world, link_release(world, release_key))
        _LINKS[key] = hit
    return hit[1]


def actual_day(world: World, release: ReleaseInfo, feature_key: str, horizon: float) -> float:
    """Day (relative to Code Freeze) the required work merged in ``world``; inf if later/never."""
    if release.code_freeze_at is None or feature_key not in world.features:
        return float("inf")
    links = _links(world, release.key)
    # Only PRs opened before release day: later ones belong to a later release's work.
    _, done = required_done_at(world.features[feature_key], world, links, release.release_at)
    if done is None:
        return float("inf")
    day = _rel(done, release.code_freeze_at)
    return day if day <= horizon else float("inf")


def baseline_days(
    events: Sequence[NormalizedEvent], world: World, release_keys: Sequence[str], lead_days: float
) -> list[float]:
    """Merge days of earlier releases' features that were in and not done at the same point.

    Uses only ``world`` (data before the forecast time) for the outcomes, and the events
    before each earlier release's own point for "in and not done".
    """
    out: list[float] = []
    for key in release_keys:
        release = world.releases[key]
        if release.code_freeze_at is None:
            continue
        point = release.code_freeze_at - timedelta(days=lead_days)
        past = project(events, point)
        horizon = grid(release, point)[-1]
        links = _links(past, key)
        for f in past.features_in(key):
            _, done_then = required_done_at(f, past, links)
            if done_then is not None:
                continue
            out.append(actual_day(world, release, f.key, horizon))
    return out


def crps(cdf: Sequence[float], days: Sequence[int], actual: float) -> float:
    """Squared distance between a forecast CDF and the step at ``actual``, one-day steps."""
    return float(sum((p - float(actual <= d)) ** 2 for p, d in zip(cdf, days, strict=True)))


def _ecdf(samples: Sequence[float], days: Sequence[int]) -> list[float]:
    arr = np.asarray(samples, dtype=np.float64)
    if arr.size == 0:
        return [0.0 for _ in days]
    return [float((arr <= d).mean()) for d in days]


def _covered(fc: MergeDateForecast, actual: float) -> bool:
    lo = fc.p10 if fc.p10 is not None else float("inf")
    hi = fc.p90 if fc.p90 is not None else float("inf")
    return lo <= actual <= hi


def backtest_dates(
    events: Sequence[NormalizedEvent],
    release_key: str,
    lead_days: Sequence[int] = (28, 14, 7, -3),
    config: ForecastConfig = DEFAULT_FORECAST,
) -> list[DateLeadResult]:
    """Forecast merge dates at each lead time and score them against what happened.

    Raises ``ValueError`` if the data does not reach the end of the release's horizon
    (release day + 14 days): open features would wrongly count as "never merged".
    """
    latest = max(e.occurred_at for e in events) + timedelta(days=1)
    final = project(events, latest)
    release = final.releases[release_key]
    if release.code_freeze_at is None:
        raise ValueError(f"{release_key} has no Code Freeze date")
    end = (release.release_at or release.code_freeze_at) + TAIL
    if latest - timedelta(days=1) < end:
        raise ValueError(f"{release_key} cannot be scored yet: its horizon ends {end:%Y-%m-%d}")

    results: list[DateLeadResult] = []
    for lead in lead_days:
        as_of = release.code_freeze_at - timedelta(days=lead)
        world = project(events, as_of)
        sources = finished_releases(world, as_of, exclude=release_key)
        calibration = calibrate(world, sources)
        fcs = forecast_release_dates(world, release_key, calibration, config)
        days = grid(world.releases[release_key], as_of)
        horizon = days[-1]
        base = baseline_days(events, world, sources, float(lead))
        base_cdf = _ecdf(base, days)
        cases: list[DateCase] = []
        for fc in fcs:
            if fc.status != "forecast" or not fc.cdf:
                continue
            actual = actual_day(final, release, fc.feature_key, horizon)
            cdf = [c[1] for c in fc.cdf]
            cases.append(
                DateCase(
                    fc.feature_key,
                    fc.p10,
                    fc.p50,
                    fc.p90,
                    actual,
                    _covered(fc, actual),
                    round(crps(cdf, days, actual), 3),
                    round(crps(base_cdf, days, actual), 3),
                )
            )
        n = len(cases)
        c = float(np.mean([x.crps for x in cases])) if cases else None
        c0 = float(np.mean([x.crps_baseline for x in cases])) if cases else None
        cov = float(np.mean([x.covered for x in cases])) if cases else None
        skill = round(1 - c / c0, 3) if c is not None and c0 else None
        curve = release_curve(world.releases[release_key], as_of, fcs)
        at_release: tuple[float, float, float] | None = None
        actual_count: int | None = None
        if curve and curve.release_day is not None:
            target = int(np.floor(curve.release_day))
            row = next((r for r in curve.forecast if r[0] == target), None)
            if row:
                at_release = (row[1], row[2], row[3])
            in_release = [f.feature_key for f in fcs if f.status in ("done", "forecast")]
            actual_count = sum(
                1 for k in in_release if actual_day(final, release, k, horizon) <= target
            )
        results.append(
            DateLeadResult(
                release=release_key,
                lead_days=lead,
                as_of=as_of.isoformat(),
                calibration_releases=tuple(sources),
                baseline_samples=len(base),
                n=n,
                merged_within_horizon=round(
                    float(np.mean([np.isfinite(x.actual) for x in cases])), 3
                )
                if cases
                else None,
                coverage=round(cov, 3) if cov is not None else None,
                crps=round(c, 3) if c is not None else None,
                crps_baseline=round(c0, 3) if c0 is not None else None,
                skill=skill,
                passes=bool(
                    cov is not None
                    and COVERAGE_RANGE[0] <= cov <= COVERAGE_RANGE[1]
                    and skill is not None
                    and skill > 0
                ),
                count_at_release_forecast=at_release,
                count_at_release_actual=actual_count,
                cases=tuple(cases),
            )
        )
    return results
