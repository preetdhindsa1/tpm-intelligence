"""Merge-date forecasts (engine/merge_date.py) on the real #6395 fixtures.

#6395's main PR #143709 opened Nov 2 and merged Nov 20 23:28 UTC, 3.48 days after Code
Freeze (Nov 17 12:00 UTC).
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from engine.backtest_dates import crps
from engine.forecast import Calibration, ForecastConfig
from engine.links import link_release
from engine.merge_date import forecast_merge_date, grid, release_curve
from engine.projection import World, project
from tests.engine.conftest import K6395, MAIN_PR, V138, fixture_events, utc

FAST = ForecastConfig(replications=8, sims=400)


def world_at(when: datetime) -> World:
    return project(fixture_events(), when)


def calibration(durations: tuple[float, ...]) -> Calibration:
    return Calibration(("kubernetes:v1.37",), utc(2026, 11, 1), durations, {}, {})


def test_done_feature_reports_when_its_main_pr_merged() -> None:
    w = world_at(utc(2026, 11, 21, 12))
    fc = forecast_merge_date(
        w.features[K6395], w.releases[V138], w, link_release(w, V138), calibration((1.0,)), FAST
    )
    assert fc.status == "done"
    assert fc.done_day == pytest.approx(3.48, abs=0.01)


def test_open_main_pr_gets_a_merge_day_distribution() -> None:
    # Nov 10: main PR #143709 open for about 8 days. Calibration PRs that took 10, 12 and
    # 20 days leave about 2, 4 and 12 more days.
    w = world_at(utc(2026, 11, 10))
    age = (w.as_of - w.pull_requests[MAIN_PR].created_at).total_seconds() / 86400
    now = -7.5  # Nov 10 00:00 is 7.5 days before Code Freeze
    expected = [now + d - age for d in (10.0, 12.0, 20.0)]
    fc = forecast_merge_date(
        w.features[K6395],
        w.releases[V138],
        w,
        link_release(w, V138),
        calibration((10.0, 12.0, 20.0)),
        FAST,
    )
    assert fc.status == "forecast"
    assert fc.p10 is not None
    assert fc.p50 is not None
    assert fc.p90 is not None
    assert expected[0] - 0.05 <= fc.p10 <= fc.p50 <= fc.p90 <= expected[2] + 0.05
    assert fc.by_freeze == pytest.approx(2 / 3, abs=0.12)  # bootstrap of 3 durations
    assert fc.by_release == 1.0
    probs = [c[1] for c in fc.cdf]
    assert probs == sorted(probs)  # a CDF never goes down
    assert all(lo <= m <= hi for _, m, lo, hi in fc.cdf)
    days = grid(w.releases[V138], w.as_of)
    assert days[0] == -8  # Nov 10
    assert days[-1] == 43  # release day Dec 16 + 14 days


def test_never_merging_calibration_puts_the_merge_beyond_the_horizon() -> None:
    w = world_at(utc(2026, 11, 10))
    fc = forecast_merge_date(
        w.features[K6395],
        w.releases[V138],
        w,
        link_release(w, V138),
        calibration((float("inf"),)),
        FAST,
    )
    assert fc.p10 is None
    assert fc.p50 is None
    assert fc.p90 is None
    assert fc.by_release == 0.0


def test_release_curve_counts_done_features_and_sums_draws() -> None:
    w = world_at(utc(2026, 11, 10))
    links = link_release(w, V138)
    cal = calibration((10.0, 12.0, 20.0))
    fcs = [
        forecast_merge_date(f, w.releases[V138], w, links, cal, FAST)
        for f in w.features_ever_in(V138)
    ]
    curve = release_curve(w.releases[V138], w.as_of, fcs)
    assert curve is not None
    assert curve.features == len(fcs)
    means = [r[1] for r in curve.forecast]
    assert means == sorted(means)
    assert all(lo <= m <= hi for _, m, lo, hi in curve.forecast)
    assert curve.forecast[-1][1] <= curve.features
    counts = [c for _, c in curve.actual]
    assert counts == sorted(counts)


def test_crps_is_zero_for_a_perfect_forecast_and_grows_with_error() -> None:
    days = list(range(-5, 6))
    perfect = [float(d >= 2) for d in days]
    assert crps(perfect, days, 2.0) == 0.0
    late = [float(d >= 4) for d in days]
    assert crps(late, days, 2.0) == pytest.approx(2.0)
    assert crps([0.0] * len(days), days, float("inf")) == 0.0
    assert np.isclose(crps([1.0] * len(days), days, float("inf")), len(days))


def test_a_closed_main_pr_is_not_treated_as_nothing_left_to_merge() -> None:
    # #6395 had #143442 closed without merging. Make it the only PR: the feature needs a
    # new PR, so it cannot be "done" and its merge day is not today.
    w = world_at(utc(2026, 11, 10))
    links = link_release(w, V138)
    closed = "kubernetes/kubernetes#143442"
    assert w.pull_requests[closed].state == "closed"

    class OnlyClosed:
        def __getattr__(self, name: str) -> object:
            return getattr(links, name)

        def verified_prs(self, key: str) -> list[str]:
            return [closed] if key == K6395 else links.verified_prs(key)

    fc = forecast_merge_date(
        w.features[K6395],
        w.releases[V138],
        w,
        OnlyClosed(),  # type: ignore[arg-type]
        calibration((10.0, 12.0, 20.0)),
        FAST,
    )
    assert fc.status == "forecast"
    assert fc.p10 is not None
    assert fc.p10 > -7.5 + 1  # a new PR must open and take a sampled duration


def test_backtest_refuses_a_release_whose_outcome_is_not_known_yet() -> None:
    from engine.backtest_dates import backtest_dates

    # The fixtures end in Nov 2026; v1.38's horizon runs to Dec 30.
    with pytest.raises(ValueError, match="cannot be scored yet"):
        backtest_dates(list(fixture_events()), V138, (7,), FAST)


def test_truth_ignores_prs_opened_after_release_day() -> None:
    from engine.merge_date import required_done_at

    w = world_at(utc(2026, 11, 21, 12))
    links = link_release(w, V138)
    _, done = required_done_at(w.features[K6395], w, links)
    assert done is not None
    # Cut-off before the main PR #143709 opened (Nov 2): it no longer counts.
    _, early = required_done_at(w.features[K6395], w, links, utc(2026, 11, 1))
    assert early != done


def test_no_earlier_release_means_no_merge_date_forecast() -> None:
    """Issue #9: an empty calibration gives no distribution, but a merged fact still shows."""
    no_history = Calibration((), utc(2026, 11, 1), (), {}, {})
    before = world_at(utc(2026, 11, 10))
    fc = forecast_merge_date(
        before.features[K6395],
        before.releases[V138],
        before,
        link_release(before, V138),
        no_history,
        FAST,
    )
    assert fc.status == "insufficient_history"
    after = world_at(utc(2026, 11, 21, 12))
    done = forecast_merge_date(
        after.features[K6395],
        after.releases[V138],
        after,
        link_release(after, V138),
        no_history,
        FAST,
    )
    assert done.status == "done"  # facts come first
