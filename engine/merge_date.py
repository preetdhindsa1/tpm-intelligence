"""When will a feature's required code merge? (M7, ADR-0005 "Merge dates"). Pure, no I/O.

The odds forecast asks "merged by Code Freeze?". This keeps the same Monte Carlo draws
(:func:`engine.forecast.simulate_completion`) and reports *when*: a distribution of the
day the feature's required work (main PR, its stated prerequisites, a new PR if one is
needed) has merged, in days relative to Code Freeze. It works after Code Freeze too, when
the question becomes "by release day?".

Days are measured relative to Code Freeze (negative = before it). Draws that never merge,
or merge after the curve's end, are "not within the horizon".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import numpy.typing as npt

from engine.forecast import (
    DEFAULT_FORECAST,
    INSUFFICIENT_HISTORY,
    Calibration,
    ForecastConfig,
    simulate_completion,
)
from engine.graph import pr_dependencies
from engine.links import ReleaseLinks, link_release
from engine.projection import Feature, ReleaseInfo, World
from engine.rules import main_pr

DAY = 86400.0
# The curve runs until this long after release day.
TAIL = timedelta(days=14)
QUANTILES = (10.0, 50.0, 90.0)


@dataclass(frozen=True)
class MergeDateForecast:
    """When a feature's required code merges, relative to Code Freeze (days)."""

    feature_key: str
    as_of: datetime
    status: str  # "done" | "forecast" | "no_freeze_date" | "insufficient_history"
    done_day: float | None = None  # status "done": when it actually merged
    # Quantiles of the merge day; None = later than the horizon (or never).
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    # P(merged by day d) for each whole day d on the release's curve grid: mean, low, high
    # across bootstrap replications.
    cdf: tuple[tuple[int, float, float, float], ...] = ()
    by_freeze: float | None = None  # P(merged by Code Freeze), unrecalibrated
    by_release: float | None = None  # P(merged by release day)
    # Every simulated merge day (relative to Code Freeze; inf = never), for summing
    # features into a release curve. Not serialised.
    draws: npt.NDArray[np.float64] | None = field(default=None, repr=False, compare=False)


def _rel_days(when: datetime, freeze: datetime) -> float:
    return (when - freeze).total_seconds() / DAY


def grid(release: ReleaseInfo, as_of: datetime) -> list[int]:
    """Whole days relative to Code Freeze from ``as_of`` to release day + ``TAIL``."""
    if release.code_freeze_at is None:
        return []
    end = release.release_at or release.code_freeze_at
    first = int(np.floor(_rel_days(as_of, release.code_freeze_at)))
    last = int(np.ceil(_rel_days(end + TAIL, release.code_freeze_at)))
    return list(range(first, last + 1))


def required_done_at(
    feature: Feature, world: World, links: ReleaseLinks, opened_before: datetime | None = None
) -> tuple[bool, datetime | None]:
    """(has PRs, when the required work merged): the main PR and its stated prerequisites.

    The main PR is chosen among PRs not closed without merging (a closed PR cannot deliver
    the code). ``opened_before`` limits it to PRs opened before a time: a backtest's truth
    uses the release day, so a long-lived KEP's PRs for later releases do not count.
    ``None`` when it (or a prerequisite) is not merged as of ``world.as_of``, or when
    every PR was closed.
    """
    keys = [
        k
        for k in links.verified_prs(feature.key)
        if k in world.pull_requests
        and (opened_before is None or world.pull_requests[k].created_at < opened_before)
    ]
    live = [k for k in keys if world.pull_requests[k].state != "closed"]
    main = main_pr(live, world, links, feature.key)
    if main is None:
        return bool(keys), None
    required = [main]
    frontier = [main]
    while frontier:
        for dep in pr_dependencies(frontier.pop()):
            pr = world.pull_requests.get(dep)
            if pr is not None and pr not in required and pr.state != "closed":
                required.append(pr)
                frontier.append(pr)
    if any(p.merged_at is None for p in required):
        return True, None
    return True, max(p.merged_at for p in required if p.merged_at is not None)


def forecast_merge_date(
    feature: Feature,
    release: ReleaseInfo,
    world: World,
    links: ReleaseLinks,
    calibration: Calibration,
    config: ForecastConfig = DEFAULT_FORECAST,
) -> MergeDateForecast:
    """Distribution of the day ``feature``'s required code merges."""
    t, freeze = world.as_of, release.code_freeze_at
    if freeze is None:
        return MergeDateForecast(feature.key, t, "no_freeze_date")
    _, done = required_done_at(feature, world, links)
    if done is not None:
        return MergeDateForecast(feature.key, t, "done", done_day=round(_rel_days(done, freeze), 2))
    if not calibration.source_releases:  # nothing measured to draw from (issue #9)
        return MergeDateForecast(feature.key, t, INSUFFICIENT_HISTORY)
    now = _rel_days(t, freeze)
    window_end = freeze if t < freeze else (release.release_at or freeze)
    draws = simulate_completion(
        feature,
        world,
        links,
        calibration,
        days_to_freeze=-now,
        new_work_window_days=max((window_end - t).total_seconds() / DAY, 0.0),
        config=config,
        skip_closed_main=True,
    )
    days = grid(release, t)
    horizon = days[-1] if days else now
    # Each draw as a day relative to Code Freeze (inf = never).
    rel = [now + when for when in draws.total]
    per_rep = np.array([[float((r <= d).mean()) for d in days] for r in rel])
    lo, hi = np.percentile(per_rep, (config.interval[0], config.interval[1]), axis=0)
    mean = per_rep.mean(axis=0)
    pooled = np.concatenate(rel)
    within = np.where(pooled <= horizon, pooled, np.inf)
    # No interpolation: between two 'never' draws there is no number to interpolate.
    qs = [float(np.percentile(within, q, method="inverted_cdf")) for q in QUANTILES]

    def q(x: float) -> float | None:
        return round(x, 1) if np.isfinite(x) else None

    def p_by(day: float) -> float:
        return round(float((pooled <= day).mean()), 3)

    release_day = _rel_days(release.release_at, freeze) if release.release_at else None
    return MergeDateForecast(
        feature.key,
        t,
        "forecast",
        p10=q(qs[0]),
        p50=q(qs[1]),
        p90=q(qs[2]),
        cdf=tuple(
            (d, round(float(m), 3), round(float(a), 3), round(float(b), 3))
            for d, m, a, b in zip(days, mean, lo, hi, strict=True)
        ),
        by_freeze=p_by(0.0) if now < 0 else None,
        by_release=p_by(release_day) if release_day is not None else None,
        draws=pooled,
    )


@dataclass(frozen=True)
class ReleaseCurve:
    """Features with their required code merged, by day: actual so far, forecast after."""

    release_key: str
    as_of: datetime
    as_of_day: float
    release_day: float | None
    features: int
    done_now: int
    # (day, expected count, low, high): done features count 1, others their P(by day).
    forecast: tuple[tuple[int, float, float, float], ...]
    # (day, count) of features whose required code had merged by that day (to as_of).
    actual: tuple[tuple[int, int], ...]


def release_curve(
    release: ReleaseInfo,
    as_of: datetime,
    forecasts: Iterable[MergeDateForecast],
    interval: tuple[float, float] = (10.0, 90.0),
) -> ReleaseCurve | None:
    """Sum the per-feature forecasts into one curve for the release.

    The range is the 10th-90th percentile of the simulated *count*: draw ``i`` of every
    feature is combined (features are simulated independently), so it covers both the
    model's randomness and the calibration uncertainty.
    """
    if release.code_freeze_at is None:
        return None
    fcs = [f for f in forecasts if f.status in ("done", "forecast")]
    days = np.array(grid(release, as_of), dtype=np.float64)
    now = _rel_days(as_of, release.code_freeze_at)
    done_days = sorted(f.done_day for f in fcs if f.status == "done" and f.done_day is not None)
    open_ = [f.draws for f in fcs if f.status == "forecast" and f.draws is not None]
    n = min((d.size for d in open_), default=1)
    counts = np.full((n, days.size), float(len(done_days)))
    for d in open_:
        counts += d[:n, None] <= days[None, :]
    lo, hi = np.percentile(counts, interval, axis=0) if days.size else ([], [])
    first = int(np.floor(done_days[0])) if done_days else int(days[0]) if days.size else 0
    start = min(first, int(days[0])) if days.size else first
    return ReleaseCurve(
        release_key=release.key,
        as_of=as_of,
        as_of_day=round(now, 2),
        release_day=round(_rel_days(release.release_at, release.code_freeze_at), 2)
        if release.release_at
        else None,
        features=len(fcs),
        done_now=len(done_days),
        forecast=tuple(
            (int(d), round(float(e), 2), round(float(a), 2), round(float(b), 2))
            for d, e, a, b in zip(days, counts.mean(axis=0), lo, hi, strict=True)
        ),
        actual=tuple(
            (d, sum(1 for x in done_days if x <= d)) for d in range(start, int(np.floor(now)) + 1)
        ),
    )


def forecast_release_dates(
    world: World,
    release_key: str,
    calibration: Calibration,
    config: ForecastConfig = DEFAULT_FORECAST,
    features: Iterable[Feature] | None = None,
    links: ReleaseLinks | None = None,
) -> list[MergeDateForecast]:
    """Merge-date forecasts for every feature in the release (or the given ones).

    ``links``: the release's linking if already computed (see ``assess_release``).
    """
    release = world.releases[release_key]
    links = links if links is not None else link_release(world, release_key)
    chosen = list(features) if features is not None else world.features_in(release_key)
    return [forecast_merge_date(f, release, world, links, calibration, config) for f in chosen]
