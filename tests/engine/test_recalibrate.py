"""Recalibration: monotone, shrunk to the base rate, trained only on earlier releases."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from engine.odds import release_odds, training_pairs
from engine.recalibrate import Recalibration, _pava, fit
from tests.engine.conftest import utc
from tests.engine.synthetic import Stream
from tests.engine.test_forecast import FAST, D, two_releases


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


R44, R45 = "kubernetes:4.4.0", "kubernetes:4.5.0"  # Kafka dates, see kafka_releases


def _cycle(s: Stream, key: str, first: int, start: datetime, freeze: datetime) -> None:
    """10 features with one PR each; 7 merge 10 days after opening, 3 slip at freeze.

    Synthetic: each feature gets its fix version 30 days before the cycle starts, so it
    is already in the release at a replay date that falls before the cycle (4.4.0 at 72
    days out is replayed at May 19, before its May 22 start).
    """
    for i in range(10):
        n = first + i
        lands = i < 7
        changes = [(start - 30 * D, True)]
        if not lands:
            changes.append((freeze + timedelta(hours=1), False))
        s.feature(n, key, changes)
        created = start + (10 + i) * D
        s.pr(first * 10 + i, n, created, merged=created + 10 * D if lands else None)


def kafka_releases(*, with_4_2: bool, history: bool = True) -> Stream:
    """Kafka's real dates (#83): Feature Freeze is the engine's Code Freeze (ADR-0018).

    The synthetic stream links PRs through KEP links, so the releases sit under its
    default project; the training rule is the same for every project.

    4.4.0 is the finished release 4.5.0 trains on; 4.3.0 and 4.2.0 matter only as the
    history 4.4.0's own replayed forecast is calibrated on. ``history=False`` loads the
    earlier releases' dates without their features and PRs.
    """
    s = Stream(utc(2026, 11, 24))
    earlier = [("4.3.0", utc(2026, 2, 17), utc(2026, 3, 19), utc(2026, 5, 22), 300)]
    if with_4_2:
        earlier.insert(0, ("4.2.0", utc(2025, 9, 2), utc(2025, 11, 20), utc(2026, 2, 17), 400))
    for name, start, freeze, shipped, first in earlier:
        key = s.release(name, start, freeze, shipped)
        if history:
            _cycle(s, key, first, start, freeze)
    r44 = s.release("4.4.0", utc(2026, 5, 22), utc(2026, 7, 30), utc(2026, 10, 26))
    _cycle(s, r44, 200, utc(2026, 5, 22), utc(2026, 7, 30))
    s.release("4.5.0", utc(2026, 10, 26), utc(2027, 2, 4), utc(2027, 3, 17))
    return s


def test_a_release_trains_only_if_a_release_before_it_had_shipped_by_its_replay_date() -> None:
    """2026-11-24: 4.5.0 is 72 days from Feature Freeze, so 4.4.0 is replayed at May 19,
    2026. 4.3.0 shipped May 22, three days later, so it cannot calibrate that replay and
    4.4.0 does not train; every 4.5.0 probability was the base rate (#83)."""
    only_4_3 = kafka_releases(with_4_2=False)
    as_of = utc(2026, 11, 24)
    assert training_pairs(only_4_3.events, R45, as_of, 72, FAST) == ([], [])
    # From 69 days out the replay date passes May 22 and 4.3.0 counts.
    _, used = training_pairs(only_4_3.events, R45, as_of, 69, FAST)
    assert used == [R44]
    # With 4.2.0 (shipped Feb 17, 2026) 4.4.0 trains at 72 days too.
    pairs, used = training_pairs(kafka_releases(with_4_2=True).events, R45, as_of, 72, FAST)
    assert used == [R44]
    assert len(pairs) == 10
    # A release record alone is not enough: without 4.2.0's PRs there is nothing to
    # calibrate 4.4.0's replay on, so it yields no pairs.
    bare = kafka_releases(with_4_2=True, history=False)
    assert training_pairs(bare.events, R45, as_of, 72, FAST)[0] == []
