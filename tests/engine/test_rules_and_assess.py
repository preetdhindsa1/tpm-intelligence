"""Freeze check, rule flags, graph and assessment on the real #6395 / #2570 history."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime

import pytest

from engine.assess import FeatureAssessment, assess_release
from engine.freeze import CodeStatus, check_pr
from engine.graph import build_graph, critical_path, pr_dependencies
from engine.links import link_release
from engine.projection import Check, Feature, PullRequest, World, project
from engine.rules import evaluate_feature, unlinked_open_load
from tests.engine.conftest import K2570, K6395, MAIN_PR, V138, fixture_events, utc

KK = "kubernetes/kubernetes"


def assessed(as_of: datetime, key: str = K6395) -> FeatureAssessment:
    report = assess_release(project(fixture_events(), as_of), V138)
    return next(f for f in report.features if f.key == key)


def codes(a: FeatureAssessment) -> set[str]:
    return {f.code for f in a.flags}


# ---------------------------------------------------------------- freeze check


@pytest.mark.parametrize(
    ("as_of", "pr", "status"),
    [
        (utc(2026, 11, 10), MAIN_PR, CodeStatus.NOT_MERGED),
        (utc(2026, 11, 21, 0), MAIN_PR, CodeStatus.MERGED_AFTER_FREEZE_NO_EXCEPTION),
        (utc(2026, 11, 21, 3), MAIN_PR, CodeStatus.MERGED_AFTER_FREEZE_WITH_EXCEPTION),
        (utc(2026, 11, 21, 3), f"{KK}#143522", CodeStatus.MERGED_BEFORE_FREEZE),
        (utc(2026, 11, 21, 3), f"{KK}#143442", CodeStatus.CLOSED_UNMERGED),
    ],
)
def test_freeze_check(as_of: datetime, pr: str, status: CodeStatus) -> None:
    world = project(fixture_events(), as_of)
    check = check_pr(world.pull_requests[pr], world.features[K6395], world.releases[V138])
    assert check.status is status
    assert check.counts == (
        status in {CodeStatus.MERGED_BEFORE_FREEZE, CodeStatus.MERGED_AFTER_FREEZE_WITH_EXCEPTION}
    )


def test_exception_evidence_is_the_readd_time() -> None:
    world = project(fixture_events(), utc(2026, 11, 21, 3))
    check = check_pr(world.pull_requests[MAIN_PR], world.features[K6395], world.releases[V138])
    assert check.exception_evidence_at == utc(2026, 11, 21, 0, 33, 55)


# ---------------------------------------------------------------- #6395 through the cycle


def test_nov_10_late_main_pr() -> None:
    a = assessed(utc(2026, 11, 10))
    [late] = [f for f in a.flags if f.code == "late_main_pr"]
    assert late.facts["pull_request"] == MAIN_PR
    assert late.facts["days_before_freeze"] == pytest.approx(14.8, abs=0.1)
    assert "main_pr_not_merged" not in codes(a)
    assert "removed_at_freeze" not in codes(a)


def test_nov_18_removed_and_main_pr_unmerged() -> None:
    a = assessed(utc(2026, 11, 18))
    assert not a.in_release
    assert {"removed_at_freeze", "main_pr_not_merged"} <= codes(a)
    assert "readded_after_freeze" not in codes(a)


def test_nov_21_readded_with_exception() -> None:
    a = assessed(utc(2026, 11, 21, 3))
    assert a.in_release
    assert {"removed_at_freeze", "readded_after_freeze", "merged_after_freeze"} <= codes(a)
    [merged] = [f for f in a.flags if f.code == "merged_after_freeze"]
    assert merged.facts["status"] == "merged_after_freeze_with_exception"
    assert a.critical_path == ()  # everything merged or closed


def test_2570_removed_at_freeze_and_readded() -> None:
    assert "removed_at_freeze" in codes(assessed(utc(2026, 11, 18), K2570))
    late = assessed(utc(2026, 11, 21, 3), K2570)
    assert {"removed_at_freeze", "readded_after_freeze"} <= codes(late)


def test_6395_prs_and_main_pr() -> None:
    a = assessed(utc(2026, 11, 21, 3))
    keys = [p.key for p in a.pull_requests]
    assert keys == [f"{KK}#{n}" for n in (143442, 143445, 143474, 143522, 143709)]
    assert [p.key for p in a.pull_requests if p.is_main] == [MAIN_PR]
    main = next(p for p in a.pull_requests if p.is_main)
    assert main.review_records == 97
    assert main.review_rounds < main.review_records
    assert a.suggested_pull_requests == (f"{KK}#143644",)


def test_6395_timeline_matches_claude_md() -> None:
    a = assessed(utc(2026, 11, 21, 3))
    wanted = [
        (e.at.isoformat(), e.kind)
        for e in a.timeline
        if e.kind
        in {
            "opted_in",
            "added_to_release",
            "tracked",
            "code_freeze",
            "removed_from_release",
            "untracked",
        }
        or (e.kind == "pr_merged" and e.ref == MAIN_PR)
    ]
    assert wanted == [
        ("2026-09-21T20:34:30+00:00", "opted_in"),
        ("2026-09-21T20:34:45+00:00", "added_to_release"),
        ("2026-09-23T06:41:32+00:00", "tracked"),
        ("2026-11-17T12:00:00+00:00", "code_freeze"),
        ("2026-11-17T12:05:57+00:00", "removed_from_release"),
        ("2026-11-17T12:05:58+00:00", "untracked"),
        ("2026-11-20T23:28:24+00:00", "pr_merged"),
        ("2026-11-21T00:33:55+00:00", "added_to_release"),
        ("2026-11-21T00:33:55+00:00", "tracked"),
    ]


# ---------------------------------------------------------------- synthetic rule cases


def _world_with(pr: PullRequest, feature: Feature, as_of: datetime) -> World:
    base = project(fixture_events(), as_of)
    return replace(base, features={feature.key: feature}, pull_requests={pr.key: pr})


def _feature(desc: str = "", tracked: bool = True) -> Feature:
    world = project(fixture_events(), utc(2026, 11, 10))
    f = world.features[K6395]
    labels = f.labels if tracked else f.labels - {"tracked/yes"}
    return replace(f, description=desc, labels=labels)


def _pr(**kw: object) -> PullRequest:
    base = PullRequest(
        key=f"{KK}#1",
        repo=KK,
        number=1,
        title="KEP-6395: impl",
        body="",
        author="a",
        labels=("sig/node",),
        created_at=utc(2026, 10, 1),
        state="open",
        merged_at=None,
        closed_at=None,
        reviews=(),
        checks=(),
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def _flags(pr: PullRequest, feature: Feature, as_of: datetime) -> set[str]:
    world = _world_with(pr, feature, as_of)
    links = link_release(world, V138)
    return {f.code for f in evaluate_feature(feature, world.releases[V138], world, links)}


def test_review_waiting_and_ci_failing() -> None:
    pr = _pr(checks=(Check("pull-kubernetes-unit", "failure", utc(2026, 10, 2)),))
    flags = _flags(pr, _feature(), utc(2026, 11, 10))
    assert {"review_waiting", "ci_failing"} <= flags


def test_no_linked_prs_for_tracked_feature() -> None:
    flags = _flags(_pr(title="unrelated"), _feature(), utc(2026, 11, 10))
    assert "no_linked_prs" in flags


def test_unlinked_load_is_per_sig_at_release_level() -> None:
    world = _world_with(
        _pr(title="unrelated", labels=("sig/storage", "sig/node")), _feature(), utc(2026, 11, 10)
    )
    links = link_release(world, V138)
    assert unlinked_open_load(world, links) == Counter({"sig/storage": 1, "sig/node": 1})
    flags = evaluate_feature(_feature(), world.releases[V138], world, links)
    assert "high_unlinked_load" not in {f.code for f in flags}


# ---------------------------------------------------------------- graph


def test_dependency_phrases() -> None:
    pr = _pr(
        body="Depends on #100. Builds on https://github.com/kubernetes/kubernetes/pull/200\n"
        "/hold until #300 merges"
    )
    assert pr_dependencies(pr) == [f"{KK}#100", f"{KK}#200", f"{KK}#300"]


def test_critical_path_is_longest_open_chain() -> None:
    a = _pr(number=1, key=f"{KK}#1", title="KEP-6395 a")
    b = _pr(number=2, key=f"{KK}#2", title="KEP-6395 b", body="depends on #1")
    c = _pr(number=3, key=f"{KK}#3", title="KEP-6395 c", body="depends on #2")
    d = _pr(number=4, key=f"{KK}#4", title="KEP-6395 d", state="merged", merged_at=utc(2026, 10, 5))
    prs = {p.key: p for p in (a, b, c, d)}
    links = {K6395: list(prs)}
    g = build_graph(V138, [_feature()], prs, links)
    assert critical_path(g, K6395, prs) == [a.key, b.key, c.key]
    heavy_c = critical_path(g, K6395, prs, weight=lambda p: 10.0 if p.number == 3 else 1.0)
    assert heavy_c[-1] == c.key


def test_critical_path_survives_dependency_cycles() -> None:
    a = _pr(number=1, key=f"{KK}#1", body="depends on #2")
    b = _pr(number=2, key=f"{KK}#2", body="depends on #1")
    prs = {a.key: a, b.key: b}
    g = build_graph(V138, [_feature()], prs, {K6395: list(prs)})
    assert len(critical_path(g, K6395, prs)) == 2


def test_review_wait_threshold_respects_config() -> None:
    from engine.rules import RuleConfig

    pr = _pr()
    world = _world_with(pr, _feature(), utc(2026, 10, 5))
    links = link_release(world, V138)
    f = _feature()
    tight = evaluate_feature(f, world.releases[V138], world, links, RuleConfig(review_wait_days=1))
    loose = evaluate_feature(f, world.releases[V138], world, links, RuleConfig(review_wait_days=30))
    assert "review_waiting" in {x.code for x in tight}
    assert "review_waiting" not in {x.code for x in loose}
