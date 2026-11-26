"""Main-PR choice scoped to the release (ADR-0032 addendum 5).

A long-lived KEP links PRs from every stage. The shape below is the common v1.36 false
no-go: the implementation merged before Code Freeze, an older attempt was closed without
merging, and next-stage work opened after the freeze is still open on release day.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from engine.assess import FeatureAssessment, PRSummary, assess_release
from engine.links import link_release
from engine.projection import project
from engine.rules import main_pr
from modules.readiness.backtest import flagged
from tests.engine.conftest import K6395, MAIN_PR, V138, fixture_events, utc
from tests.engine.synthetic import Stream

D = timedelta(days=1)
FREEZE = utc(2026, 3, 18, 12)
RELEASE = utc(2026, 4, 22)


def _stream(*, with_impl: bool = True) -> tuple[Stream, str]:
    s = Stream(utc(2026, 11, 26))
    key = s.release("v1.36", utc(2026, 1, 12), FREEZE, RELEASE)
    s.feature(700, key, [(utc(2026, 1, 20), True)])
    if with_impl:
        s.pr(9001, 700, utc(2026, 2, 1), merged=utc(2026, 3, 1))  # implementation
    s.pr(9002, 700, utc(2026, 3, 10), closed=utc(2026, 3, 12))  # abandoned attempt
    s.pr(9003, 700, utc(2026, 4, 1))  # next stage, opened after the freeze, still open
    return s, key


def _feature(s: Stream, key: str, when: datetime) -> FeatureAssessment:
    a = assess_release(project(s.events, when), key)
    return next(f for f in a.features if f.key.endswith("#700"))


def _main(f: FeatureAssessment) -> PRSummary | None:
    return next((p for p in f.pull_requests if p.is_main), None)


def test_release_day_main_pr_is_the_merged_implementation() -> None:
    s, key = _stream()
    f = _feature(s, key, RELEASE)
    main = _main(f)
    assert main is not None
    assert main.key.endswith("#9001")
    assert "main_pr_not_merged" not in {fl.code for fl in f.flags}
    assert not flagged(f)


def test_the_odds_model_keeps_its_backtested_choice() -> None:
    s, key = _stream()
    world = project(s.events, RELEASE)
    links = link_release(world, key)
    feature = next(k for k in world.features if k.endswith("#700"))
    chosen = main_pr(links.verified_prs(feature), world, links, feature)
    assert chosen is not None
    assert chosen.key.endswith("#9003")


def test_only_post_freeze_work_falls_back_to_it() -> None:
    s, key = _stream(with_impl=False)
    f = _feature(s, key, RELEASE)
    main = _main(f)
    assert main is not None
    assert main.key.endswith("#9003")  # not the abandoned #9002
    assert flagged(f)


def test_an_abandoned_pr_is_main_only_when_it_is_the_only_pr() -> None:
    s, key = _stream(with_impl=False)
    f = _feature(s, key, FREEZE - D)
    main = _main(f)
    assert main is not None
    assert main.key.endswith("#9002")  # only PR so far: kept as last resort


def test_6395_main_pr_is_still_143709() -> None:
    for when in (utc(2026, 11, 10), utc(2026, 11, 18), utc(2026, 11, 21, 3)):
        a = assess_release(project(fixture_events(), when), V138)
        f = next(x for x in a.features if x.key == K6395)
        assert next(p.key for p in f.pull_requests if p.is_main) == MAIN_PR
