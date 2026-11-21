"""Recalibration: monotone, shrunk to the base rate, trained only on earlier releases."""

from __future__ import annotations

import pytest

from engine.odds import release_odds, training_pairs
from engine.recalibrate import Recalibration, _pava, fit
from tests.engine.conftest import utc
from tests.engine.synthetic import Stream
from tests.engine.test_forecast import FAST, two_releases


def test_pava_makes_values_non_decreasing() -> None:
    assert _pava([0.5, 0.3, 0.7], [1, 1, 1]) == [0.4, 0.4, 0.7]
    assert _pava([0.1, 0.2, 0.3], [1, 1, 1]) == [0.1, 0.2, 0.3]
    out = _pava([0.9, 0.1, 0.5, 0.2], [3, 1, 1, 1])
    assert out == sorted(out)


def test_overconfident_low_scores_are_pulled_up() -> None:
    """The 2026-11-21 failure: raw ~5% scores landed ~70% of the time."""
    pairs = [(0.05, i % 10 < 7) for i in range(50)] + [(0.95, i % 10 < 8) for i in range(50)]
    recal = fit(pairs, base_rate=0.75)
    assert recal.apply(0.05) == pytest.approx((35 + 4 * 0.75) / (50 + 4), abs=1e-3)
    assert recal.apply(0.95) > recal.apply(0.05)
    assert list(recal.values) == sorted(recal.values)


def test_empty_bins_fall_back_to_base_rate() -> None:
    recal = fit([(0.05, True)] * 3, base_rate=0.6)
    assert recal.apply(0.5) == pytest.approx(0.6, abs=0.05)


def test_no_training_maps_everything_to_base_rate() -> None:
    recal = fit([], base_rate=0.7)
    assert {recal.apply(p) for p in (0.0, 0.5, 1.0)} == {0.7}
    assert Recalibration.identity_to_base(0.3).apply(0.99) == 0.3


def three_releases() -> Stream:
    s, _, _ = two_releases()  # v1.37 finished, v1.38 in progress
    r0 = s.release("v1.36", utc(2026, 1, 12), utc(2026, 3, 19, 12), utc(2026, 4, 22))
    for i in range(6):
        n = 50 + i
        s.feature(
            n, r0, [(utc(2026, 1, 20), True)] + ([] if i < 3 else [(utc(2026, 3, 19, 13), False)])
        )
        s.pr(4000 + i, n, utc(2026, 2, 1), merged=utc(2026, 2, 13) if i < 3 else None)
    return s


def test_training_uses_only_releases_finished_before_as_of() -> None:
    s = three_releases()
    # Oct 2026: v1.36 and v1.37 finished; v1.36 has nothing before it, so only v1.37 trains.
    pairs, used = training_pairs(s.events, "kubernetes:v1.38", utc(2026, 10, 20), 28, FAST)
    assert used == ["kubernetes:v1.37"]
    assert len(pairs) == 10
    # June 2026: v1.37 not finished, v1.36 has no history before it -> no training.
    assert training_pairs(s.events, "kubernetes:v1.37", utc(2026, 6, 25), 28, FAST) == ([], [])


def test_release_odds_keep_raw_and_calibrated() -> None:
    s = three_releases()
    s.feature(1, "kubernetes:v1.38", [(utc(2026, 9, 1), True)])
    s.pr(9001, 1, utc(2026, 10, 15))
    odds = release_odds(s.events, "kubernetes:v1.38", utc(2026, 10, 20), FAST)
    [fc] = [f for f in odds.forecasts if f.feature_key.endswith("#1")]
    assert fc.raw_probability is not None
    assert fc.probability == odds.recalibration.apply(fc.raw_probability)
    assert fc.low is not None
    assert fc.high is not None
    assert fc.low <= fc.probability <= fc.high
