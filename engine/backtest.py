"""Backtest the forecast on a past release (CLAUDE.md section 2.5: measure, don't claim).

For each lead time ``L`` before the release's Code Freeze ``F``:

1. ``as_of = F - L``. Project the world from events dated before ``as_of`` only.
2. Calibrate on releases that had finished by ``as_of``.
3. Forecast every feature in the release at ``as_of``.
4. Score against the outcome: still in the release 3 days after ``F``.

Raw Monte Carlo odds are recalibrated on earlier releases (engine/recalibrate.py); both are
scored. The baseline is the calibration releases' landing rate for the same days-to-freeze
bucket (climatology). Skill = 1 - Brier / Brier_baseline (positive beats the base rate).
AUC measures ranking only.
Pure, no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from engine.forecast import (
    DEFAULT_FORECAST,
    ForecastConfig,
    Rate,
    bucket,
    landed,
    outcome_cutoff,
)
from engine.odds import release_odds
from engine.projection import project
from pipeline.events import NormalizedEvent

RELIABILITY_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0000001)


@dataclass(frozen=True)
class Case:
    """One forecast and its outcome."""

    feature_key: str
    probability: float  # recalibrated
    raw_probability: float
    low: float
    high: float
    baseline: float
    landed: bool


@dataclass(frozen=True)
class LeadResult:
    """Scores at one lead time."""

    release: str
    lead_days: int
    as_of: str
    calibration_releases: tuple[str, ...]
    n: int
    landed_share: float | None
    brier: float | None
    brier_raw: float | None
    brier_baseline: float | None
    skill: float | None
    skill_raw: float | None
    auc: float | None
    recalibration_training: tuple[str, ...]
    reliability: tuple[tuple[str, int, float | None, float | None], ...]  # bin, n, mean p, hit
    cases: tuple[Case, ...]


def brier(pairs: Sequence[tuple[float, bool]]) -> float | None:
    """Mean squared error of probabilities against 0/1 outcomes."""
    if not pairs:
        return None
    return sum((p - float(y)) ** 2 for p, y in pairs) / len(pairs)


def auc(pairs: Sequence[tuple[float, bool]]) -> float | None:
    """Probability that a random landed feature scores above a random slipped one."""
    pos = [p for p, y in pairs if y]
    neg = [p for p, y in pairs if not y]
    if not pos or not neg:
        return None
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def _skill(b: float | None, b0: float | None) -> float | None:
    return round(1 - b / b0, 3) if b is not None and b0 else None


def _reliability(cases: Sequence[Case]) -> tuple[tuple[str, int, float | None, float | None], ...]:
    rows: list[tuple[str, int, float | None, float | None]] = []
    for lo, hi in pairwise(RELIABILITY_EDGES):
        sel = [c for c in cases if lo <= c.probability < hi]
        label = f"{lo:.1f}-{min(hi, 1.0):.1f}"
        if not sel:
            rows.append((label, 0, None, None))
            continue
        rows.append(
            (
                label,
                len(sel),
                round(sum(c.probability for c in sel) / len(sel), 3),
                round(sum(c.landed for c in sel) / len(sel), 3),
            )
        )
    return tuple(rows)


def backtest(
    events: Sequence[NormalizedEvent],
    release_key: str,
    lead_days: Sequence[int] = (28, 14, 7),
    config: ForecastConfig = DEFAULT_FORECAST,
) -> list[LeadResult]:
    """Run the forecast at each lead time before the release's Code Freeze and score it."""
    final = project(events, _far_future(events))
    release = final.releases[release_key]
    if release.code_freeze_at is None:
        raise ValueError(f"{release_key} has no Code Freeze date")
    cutoff = outcome_cutoff(release)
    if cutoff is None:
        raise ValueError(f"{release_key} has no outcome date")
    truth = project(events, cutoff + timedelta(seconds=1))

    results: list[LeadResult] = []
    for lead in lead_days:
        as_of = release.code_freeze_at - timedelta(days=lead)
        odds = release_odds(events, release_key, as_of, config)
        baseline = odds.calibration.landing.get(bucket(float(lead)), Rate(0, 0)).mean
        raw_by_key = {fc.feature_key: fc.probability for fc in odds.raw}
        cases: list[Case] = []
        for fc in odds.forecasts:
            outcome = (
                landed(truth.features[fc.feature_key], release)
                if fc.feature_key in truth.features
                else None
            )
            raw = raw_by_key.get(fc.feature_key)
            if (
                fc.probability is None
                or fc.low is None
                or fc.high is None
                or raw is None
                or outcome is None
            ):
                continue
            cases.append(
                Case(fc.feature_key, fc.probability, raw, fc.low, fc.high, baseline, outcome)
            )
        b = brier([(c.probability, c.landed) for c in cases])
        b_raw = brier([(c.raw_probability, c.landed) for c in cases])
        b0 = brier([(c.baseline, c.landed) for c in cases])
        a = auc([(c.raw_probability, c.landed) for c in cases])
        results.append(
            LeadResult(
                release=release_key,
                lead_days=lead,
                as_of=as_of.isoformat(),
                calibration_releases=odds.calibration.source_releases,
                n=len(cases),
                landed_share=round(sum(c.landed for c in cases) / len(cases), 3) if cases else None,
                brier=round(b, 4) if b is not None else None,
                brier_raw=round(b_raw, 4) if b_raw is not None else None,
                brier_baseline=round(b0, 4) if b0 is not None else None,
                skill=_skill(b, b0),
                skill_raw=_skill(b_raw, b0),
                auc=round(a, 3) if a is not None else None,
                recalibration_training=odds.recalibration.training_releases,
                reliability=_reliability(cases),
                cases=tuple(cases),
            )
        )
    return results


def _far_future(events: Sequence[NormalizedEvent]) -> datetime:
    latest = max(e.occurred_at for e in events)
    return latest + timedelta(days=1)
