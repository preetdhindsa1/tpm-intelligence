"""Readiness backtest (#184) on the real #6395 / #2570 history, and the pass rule."""

from __future__ import annotations

from engine.assess import assess_release
from engine.projection import project
from modules.readiness.backtest import ReleaseResult, judge, replay_release
from tests.engine.conftest import V138, fixture_events, utc


def test_v138_freeze_replay_on_the_real_fixture() -> None:
    events = fixture_events()
    r = replay_release(V138, lambda when: assess_release(project(events, when), V138),
                       project(events, utc(2026, 11, 22)))  # fmt: skip
    # Both were in v1.38 at the freeze and out at the cutoff (removed Nov 17, back Nov 21).
    assert (r.features, r.slipped) == (2, 2)
    # #6395's main PR was unmerged at the freeze: flagged. #2570 has no linked PR: not flagged.
    assert (r.flagged, r.flagged_slipped) == (1, 1)
    assert (r.shipped, r.false_no_go) == (None, None)  # released Dec 16, after this world
    assert not r.counts  # 2 features: reported, not counted


def rr(n: int, slipped: int, flagged: int, hit: int, shipped: int, fng: int) -> ReleaseResult:
    return ReleaseResult("kubernetes:vX", n, slipped, flagged, hit, shipped, fng, n >= 20)


def test_the_pass_rule() -> None:
    good = judge([rr(100, 20, 25, 15, 80, 2)])  # recall .75, precision .6 vs .2, fng .025
    assert good.passed
    assert (good.recall, good.precision, good.base_rate) == (0.75, 0.6, 0.2)
    weak = judge([rr(100, 20, 60, 15, 80, 10)])  # precision .25 < .35; fng .125
    assert not weak.passed
    assert "precision" in weak.reason
    assert "false no-go" in weak.reason
    assert not judge([rr(10, 5, 5, 5, 5, 0)]).passed  # too small to count
