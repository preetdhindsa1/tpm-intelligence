"""Monte Carlo forecast, calibration and backtest on synthetic streams."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from engine.backtest import backtest, brier
from engine.forecast import (
    Calibration,
    ForecastConfig,
    Rate,
    bucket,
    calibrate,
    finished_releases,
    forecast_feature,
)
from engine.links import link_release
from engine.projection import project
from tests.engine.conftest import utc
from tests.engine.synthetic import Stream

D = timedelta(days=1)
FAST = ForecastConfig(replications=10, sims=300)
OBS = utc(2026, 12, 1)


def two_releases() -> tuple[Stream, str, str]:
    """R1 (finished): 10 features; 6 land (PRs merge in ~10 days), 4 slip (PRs never merge).
    R2 (in progress): freeze 2026-11-17."""
    s = Stream(OBS)
    r1 = s.release("v1.37", utc(2026, 5, 18), utc(2026, 7, 23, 12), utc(2026, 8, 26))
    r2 = s.release("v1.38", utc(2026, 8, 31), utc(2026, 11, 17, 12), utc(2026, 12, 16))
    for i in range(10):
        n = 100 + i
        lands = i < 6
        changes = [(utc(2026, 5, 20), True)]
        if not lands:
            changes.append((utc(2026, 7, 23, 13), False))
        s.feature(n, r1, changes)
        created = utc(2026, 6, 1) + i * D
        s.pr(5000 + i, n, created, merged=created + 10 * D if lands else None)
    return s, r1, r2


def test_bucket_edges() -> None:
    assert [bucket(d) for d in (0, 6.9, 7, 13.9, 14, 27, 28, 55, 56, 300)] == [
        0,
        0,
        1,
        1,
        2,
        2,
        3,
        3,
        4,
        4,
    ]


def test_calibration_measures_durations_and_rates() -> None:
    s, r1, _ = two_releases()
    world = project(s.events, utc(2026, 10, 1))
    cal = calibrate(world, [r1])
    assert cal.source_releases == (r1,)
    assert sorted(cal.durations_days) == [10.0] * 6 + [float("inf")] * 4
    # 21 days before freeze every R1 feature already had its PR; none got a new one.
    assert cal.new_pr[(bucket(21), True)] == Rate(0, 10)
    assert cal.landing[bucket(21)] == Rate(6, 10)
    assert cal.describe()["pr_never_merged_share"] == 0.4


def test_finished_releases_only() -> None:
    s, r1, r2 = two_releases()
    world = project(s.events, utc(2026, 10, 1))
    assert finished_releases(world, utc(2026, 10, 1), exclude=r2) == [r1]
    assert finished_releases(world, utc(2026, 8, 1), exclude=r2) == []


def _forecast(s: Stream, r2: str, n: int, as_of: datetime, cal: Calibration) -> object:
    world = project(s.events, as_of)
    return forecast_feature(
        world.features[f"kubernetes/enhancements#{n}"],
        world.releases[r2],
        world,
        link_release(world, r2),
        cal,
        FAST,
    )


@pytest.fixture
def setup() -> tuple[Stream, str, str, Calibration]:
    s, r1, r2 = two_releases()
    cal = calibrate(project(s.events, utc(2026, 10, 1)), [r1])
    return s, r1, r2, cal


def test_young_open_pr_well_before_freeze_has_good_odds(setup: tuple) -> None:  # type: ignore[type-arg]
    s, _, r2, cal = setup
    s.feature(1, r2, [(utc(2026, 9, 1), True)])
    s.pr(9001, 1, utc(2026, 10, 20))
    fc = _forecast(s, r2, 1, utc(2026, 10, 21), cal)
    assert fc.status == "forecast"  # type: ignore[attr-defined]
    # 60% of calibration PRs merge in 10 days; 27 days remain.
    assert fc.probability == pytest.approx(0.6, abs=0.1)  # type: ignore[attr-defined]
    assert fc.low <= fc.probability <= fc.high  # type: ignore[attr-defined]


def test_pr_older_than_every_merged_calibration_pr_cannot_land(setup: tuple) -> None:  # type: ignore[type-arg]
    s, _, r2, cal = setup
    s.feature(2, r2, [(utc(2026, 9, 1), True)])
    s.pr(9002, 2, utc(2026, 9, 2))  # 49 days old at as_of; calibration merges took 10 days
    fc = _forecast(s, r2, 2, utc(2026, 10, 21), cal)
    assert fc.probability == 0.0  # type: ignore[attr-defined]


def test_all_prs_merged_and_no_new_work_lands(setup: tuple) -> None:  # type: ignore[type-arg]
    s, _, r2, cal = setup
    s.feature(3, r2, [(utc(2026, 9, 1), True)])
    s.pr(9003, 3, utc(2026, 9, 5), merged=utc(2026, 9, 15))
    fc = _forecast(s, r2, 3, utc(2026, 10, 27), cal)
    # q for (bucket 21 days, has PRs) measured 0/10 -> posterior mean 1/12; the rest land.
    assert fc.probability > 0.85  # type: ignore[attr-defined]
    assert fc.open_prs == ()  # type: ignore[attr-defined]


def test_feature_without_prs_needs_new_work(setup: tuple) -> None:  # type: ignore[type-arg]
    s, _, r2, cal = setup
    s.feature(4, r2, [(utc(2026, 9, 1), True)])
    fc = _forecast(s, r2, 4, utc(2026, 10, 27), cal)
    assert fc.probability < 0.3  # type: ignore[attr-defined]


def test_dependency_blocks_child(setup: tuple) -> None:  # type: ignore[type-arg]
    s, _, r2, cal = setup
    s.feature(5, r2, [(utc(2026, 9, 1), True)])
    s.pr(9050, 5, utc(2026, 9, 2))  # too old: never merges in the model
    s.pr(9051, 5, utc(2026, 10, 20), extra="Depends on #9050")
    fc = _forecast(s, r2, 5, utc(2026, 10, 21), cal)
    assert fc.pr_on_time["kubernetes/kubernetes#9051"] == 0.0  # type: ignore[attr-defined]


def test_after_freeze_has_no_forecast(setup: tuple) -> None:  # type: ignore[type-arg]
    s, _, r2, cal = setup
    s.feature(6, r2, [(utc(2026, 9, 1), True)])
    fc = _forecast(s, r2, 6, utc(2026, 11, 18), cal)
    assert (fc.status, fc.probability) == ("after_freeze", None)  # type: ignore[attr-defined]


def test_fixed_seed_is_reproducible(setup: tuple) -> None:  # type: ignore[type-arg]
    s, _, r2, cal = setup
    s.feature(7, r2, [(utc(2026, 9, 1), True)])
    s.pr(9007, 7, utc(2026, 10, 15))
    a = _forecast(s, r2, 7, utc(2026, 10, 21), cal)
    b = _forecast(s, r2, 7, utc(2026, 10, 21), cal)
    assert a == b


def test_backtest_scores_a_finished_release() -> None:
    s, _, _ = two_releases()
    r0 = s.release("v1.36", utc(2026, 1, 12), utc(2026, 3, 19, 12), utc(2026, 4, 22))
    for i in range(6):  # calibration for v1.37: half land
        n = 50 + i
        s.feature(
            n, r0, [(utc(2026, 1, 20), True)] + ([] if i < 3 else [(utc(2026, 3, 19, 13), False)])
        )
        created = utc(2026, 2, 1) + i * D
        s.pr(4000 + i, n, created, merged=created + 12 * D if i < 3 else None)
    [result] = backtest(s.events, "kubernetes:v1.37", lead_days=(28,), config=FAST)
    assert result.calibration_releases == ("kubernetes:v1.36",)
    assert result.n == 10
    assert result.landed_share == 0.6
    assert result.brier is not None
    assert 0.0 <= result.brier <= 1.0
    assert sum(row[1] for row in result.reliability) == 10


def test_brier() -> None:
    assert brier([(1.0, True), (0.0, False)]) == 0.0
    assert brier([(0.5, True), (0.5, False)]) == 0.25
    assert brier([]) is None
