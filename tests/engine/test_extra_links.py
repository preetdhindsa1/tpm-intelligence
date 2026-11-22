"""AI suggestions and people's decisions merged into rule links (ADR-0011)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from engine.links import link_release, unlinked_pull_requests
from engine.projection import World, project
from linker.methods import LinkMethod, LinkStatus
from linker.rules import LinkCandidate
from tests.engine.conftest import K2570, K6395, MAIN_PR, V138, fixture_events, utc

PASSING = "kubernetes/kubernetes#143644"  # passing mention: rule link stays suggested
NEW = "kubernetes/kubernetes#150000"  # a PR no rule links


def world(*extra: LinkCandidate) -> World:
    w = project(fixture_events(), utc(2026, 11, 22))
    pr = replace(w.pull_requests[MAIN_PR], key=NEW, number=150000, title="kubelet: tidy", body="")
    return replace(w, pull_requests={**w.pull_requests, NEW: pr}, extra_links=extra)


def ai(pr: str, item: str, status: LinkStatus) -> LinkCandidate:
    return LinkCandidate(pr, item, LinkMethod.AI_SUGGESTED, status, Decimal("0.3"), {})


def test_new_pr_is_unlinked_until_a_suggestion_exists() -> None:
    w = world()
    assert unlinked_pull_requests(w, V138, link_release(w, V138)) == [NEW]
    w = world(ai(NEW, K6395, LinkStatus.SUGGESTED))
    assert unlinked_pull_requests(w, V138, link_release(w, V138)) == []


def test_ai_suggestion_is_shown_but_never_counted() -> None:
    links = link_release(world(ai(NEW, K6395, LinkStatus.SUGGESTED)), V138)
    assert NEW in links.suggested_prs(K6395)
    assert NEW not in links.verified_prs(K6395)


def test_person_confirmed_link_counts() -> None:
    links = link_release(world(ai(NEW, K6395, LinkStatus.VERIFIED)), V138)
    assert NEW in links.verified_prs(K6395)
    assert links.best[(NEW, K6395)].method is LinkMethod.AI_SUGGESTED


def test_confirming_a_rule_suggestion_upgrades_it() -> None:
    links = link_release(world(ai(PASSING, K6395, LinkStatus.VERIFIED)), V138)
    assert PASSING in links.verified_prs(K6395)


def test_rejection_removes_a_rule_suggestion() -> None:
    links = link_release(world(ai(PASSING, K6395, LinkStatus.REJECTED)), V138)
    assert PASSING not in links.suggested_prs(K6395)
    assert (PASSING, K6395) not in links.best


def test_rule_verified_link_is_never_changed() -> None:
    links = link_release(world(ai(MAIN_PR, K6395, LinkStatus.REJECTED)), V138)
    assert links.best[(MAIN_PR, K6395)].method is LinkMethod.EXPLICIT_KEY
    assert MAIN_PR in links.verified_prs(K6395)


def test_links_to_features_outside_the_release_or_unknown_prs_are_ignored() -> None:
    links = link_release(
        world(
            ai(NEW, "kubernetes/enhancements#1", LinkStatus.VERIFIED),
            ai("kubernetes/kubernetes#1", K2570, LinkStatus.VERIFIED),
        ),
        V138,
    )
    assert (NEW, "kubernetes/enhancements#1") not in links.best
    assert ("kubernetes/kubernetes#1", K2570) not in links.best
