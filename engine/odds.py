"""End-to-end odds for a release at a time: calibrate, simulate, recalibrate. Pure, no I/O.

Every step uses only data dated before ``as_of`` and only releases finished before it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from engine.forecast import (
    DEFAULT_FORECAST,
    LANDED_WINDOW,
    Calibration,
    Forecast,
    ForecastConfig,
    Rate,
    bucket,
    calibrate,
    finished_releases,
    forecast_release,
    landed,
)
from engine.projection import World, project
from engine.recalibrate import Recalibration, fit
from pipeline.events import NormalizedEvent


@dataclass(frozen=True)
class ReleaseOdds:
    """Calibrated forecasts for one release at one time, with everything used to make them."""

    as_of: datetime
    release_key: str
    calibration: Calibration
    recalibration: Recalibration
    raw: tuple[Forecast, ...]
    forecasts: tuple[Forecast, ...]  # recalibrated


def _lead_days(world: World, release_key: str) -> float | None:
    freeze = world.releases[release_key].code_freeze_at
    if freeze is None or world.as_of >= freeze:
        return None
    return (freeze - world.as_of).total_seconds() / 86400


def raw_forecasts(
    events: Sequence[NormalizedEvent],
    release_key: str,
    as_of: datetime,
    config: ForecastConfig = DEFAULT_FORECAST,
    world: World | None = None,
) -> tuple[World, Calibration, list[Forecast]]:
    """Uncalibrated Monte Carlo odds using releases finished before ``as_of``."""
    world = world or project(events, as_of)
    calibration = calibrate(world, finished_releases(world, as_of, exclude=release_key))
    return world, calibration, forecast_release(world, release_key, calibration, config)


def training_pairs(
    events: Sequence[NormalizedEvent],
    release_key: str,
    as_of: datetime,
    lead_days: float,
    config: ForecastConfig = DEFAULT_FORECAST,
) -> tuple[list[tuple[float, bool]], list[str]]:
    """(raw p, landed) on earlier releases, each forecast at ``lead_days`` before its freeze."""
    world = project(events, as_of)
    pairs: list[tuple[float, bool]] = []
    used: list[str] = []
    for key in finished_releases(world, as_of, exclude=release_key):
        release = world.releases[key]
        if release.code_freeze_at is None:
            continue
        t = release.code_freeze_at - timedelta(days=lead_days)
        past = project(events, t)
        if not finished_releases(past, t, exclude=key):
            continue  # nothing earlier to calibrate this release's raw forecast on
        _, _, raw = raw_forecasts(events, key, t, config, world=past)
        truth = project(events, release.code_freeze_at + LANDED_WINDOW + timedelta(seconds=1))
        for fc in raw:
            outcome = (
                landed(truth.features[fc.feature_key], release)
                if fc.feature_key in truth.features
                else None
            )
            if fc.probability is not None and outcome is not None:
                pairs.append((fc.probability, outcome))
        used.append(key)
    return pairs, used


def release_odds(
    events: Sequence[NormalizedEvent],
    release_key: str,
    as_of: datetime,
    config: ForecastConfig = DEFAULT_FORECAST,
) -> ReleaseOdds:
    """Raw forecasts recalibrated on earlier releases at the same lead time."""
    world, calibration, raw = raw_forecasts(events, release_key, as_of, config)
    lead = _lead_days(world, release_key)
    rate = calibration.landing.get(bucket(lead if lead is not None else 0.0), Rate(0, 0))
    base = rate.mean
    if lead is None:
        recal = Recalibration.identity_to_base(base)
    else:
        pairs, used = training_pairs(events, release_key, as_of, lead, config)
        recal = fit(pairs, base_rate=base, training_releases=used)

    def adjust(fc: Forecast) -> Forecast:
        if fc.probability is None or fc.low is None or fc.high is None:
            return fc
        return replace(
            fc,
            probability=recal.apply(fc.probability),
            low=recal.apply(fc.low),
            high=recal.apply(fc.high),
            raw_probability=fc.probability,
        )

    return ReleaseOdds(
        as_of, release_key, calibration, recal, tuple(raw), tuple(adjust(fc) for fc in raw)
    )
