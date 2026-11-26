"""Retro facts on the real #6395 / #2570 history, replayed day by day (ADR-0032 add. 2)."""

from __future__ import annotations

from datetime import timedelta
from itertools import pairwise

import pytest

from engine.assess import assess_release
from engine.projection import project
from modules.retro.facts import (
    MIN_GROUP,
    DayFacts,
    FeatureRow,
    RetroRun,
    patterns,
    replay_days,
    retro,
    same_day,
)
from tests.engine.conftest import K2570, K6395, V138, fixture_events, utc

NOW = utc(2026, 11, 22)


def run() -> RetroRun:
    events = fixture_events()

    def replay(day):  # type: ignore[no-untyped-def]
        return assess_release(project(events, day), V138)  # project() applies the as-of

    return retro(V138, replay, project(events, NOW), NOW)


def test_6395_is_a_late_exception_warned_three_weeks_ahead() -> None:
    r = run()
    s = {x.feature_key: x for x in r.slips}
    six = s[K6395]
    assert six.slip == "late_exception"  # out at the cutoff (Nov 20), re-added Nov 21
    assert six.slipped_at == utc(2026, 11, 17, 12, 5, 57)
    # A linked PR's failing check on Oct 27 came before the late main PR (opened Nov 2).
    assert (six.first_warning_flag, six.first_warning_at) == ("ci_failing", utc(2026, 10, 27, 12))
    assert six.lead_time_days == 21.0
    two = s[K2570]  # removed at the freeze, re-added Nov 21, no linked PR: no warning
    assert (two.slip, two.first_warning_at, two.lead_time_days) == ("late_exception", None, None)
    assert r.totals()["slips"] == len(r.slips)


def test_warnings_come_only_from_what_was_known_that_day() -> None:
    r = run()
    risk = {d.at: d.features_at_risk for d in r.days}
    assert risk[utc(2026, 10, 26, 12)] == 0
    assert risk[utc(2026, 10, 27, 12)] == 1
    assert r.days[-1].at == r.cutoff == utc(2026, 11, 20, 12)


def test_totals_count_warned_slips_and_false_alarms() -> None:
    t = run().totals()
    assert t == {"slips": 2, "warned": 1, "average_lead_time_days": 21.0,
                 "median_lead_time_days": 21.0, "planned": 2, "warned_landed": 0}  # fmt: skip


def test_no_retro_before_the_outcome_is_known() -> None:
    events = fixture_events()
    with pytest.raises(ValueError, match="no outcome yet"):
        retro(V138, lambda d: None, project(events, utc(2026, 11, 19)), NOW)  # type: ignore[arg-type,return-value]


def test_replay_days_are_daily_at_noon_and_end_at_the_cutoff() -> None:
    world = project(fixture_events(), NOW)
    days = replay_days(world.releases[V138], utc(2026, 11, 20, 12))
    assert days[0] == utc(2026, 9, 30, 12)
    assert all(b - a == timedelta(days=1) for a, b in pairwise(days))


def test_patterns_need_ten_features_per_pool() -> None:
    def rows(pool: str, n: int, slipped: int) -> tuple[FeatureRow, ...]:
        return tuple(FeatureRow(f"{pool}#{i}", pool, i < slipped,
                                ("late_main_pr",) if i % 2 else ()) for i in range(n))  # fmt: skip

    big = RetroRun("kubernetes:v1.37", NOW, NOW, "retro-1", 12, (), 0, (),
                   rows("sig/node", MIN_GROUP + 2, 3) + rows("sig/apps", 4, 1))  # fmt: skip
    shown, suppressed = patterns([big])
    assert suppressed == 1
    assert {(p.pool, p.pattern, p.value, p.n) for p in shown} == {
        ("sig/node", "slipped", 0.25, 12), ("sig/node", "late_main_pr", 0.5, 12)}  # fmt: skip


def test_same_day_picks_the_replay_on_or_before() -> None:
    days = [DayFacts(utc(2026, 11, d, 12), 2, 1, 0) for d in (10, 11, 12)]
    assert same_day(days, utc(2026, 11, 11, 18)) == days[1]
    assert same_day(days, utc(2026, 11, 1)) is None
