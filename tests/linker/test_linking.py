"""Linker rules on the real #6395 fixtures plus edge cases (ADR-0004)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from linker.methods import LinkMethod, LinkStatus
from linker.refs import Where, find_kep_refs, numbers_in, tracked_pull_requests
from linker.rules import (
    LinkCandidate,
    LinkIndex,
    PullRequestInfo,
    WorkItemInfo,
    best_links,
    link_pull_request,
)
from tests.collectors.conftest import load_json

K6395 = "kubernetes/enhancements#6395"
K1432 = "kubernetes/enhancements#1432"


def pr_info(node: dict[str, Any]) -> PullRequestInfo:
    repo = node["repository"]["nameWithOwner"]
    return PullRequestInfo(
        key=f"{repo}#{node['number']}",
        repo=repo,
        number=node["number"],
        title=node["title"],
        body=node["body"] or "",
        labels=tuple(n["name"] for n in node["labels"]["nodes"]),
    )


@pytest.fixture(scope="module")
def index() -> LinkIndex:
    issue = load_json("issue_6395.json")
    kep_6395 = WorkItemInfo(
        key=K6395,
        number=6395,
        description=issue["body"],
        feature_flags=("DynamicNodeLocalEphemeralVolumes",),
        labels=tuple(label["name"] for label in issue["labels"]),
    )
    kep_1432 = WorkItemInfo(key=K1432, number=1432, labels=("sig/storage",))
    return LinkIndex.build([kep_6395, kep_1432])


@pytest.fixture(scope="module")
def links(index: LinkIndex) -> dict[int, dict[tuple[str, str], LinkCandidate]]:
    return {
        node["number"]: best_links(link_pull_request(pr_info(node), index))
        for node in load_json("prs_6395.json")
    }


def best(links: dict[int, Any], pr: int, item: str = K6395) -> LinkCandidate | None:
    found: LinkCandidate | None = links[pr].get((f"kubernetes/kubernetes#{pr}", item))
    return found


# ---------------------------------------------------------------- real fixtures


@pytest.mark.parametrize("pr", [143442, 143445, 143474, 143522, 143709])
def test_tracking_list_prs_are_verified(links: dict[int, Any], pr: int) -> None:
    link = best(links, pr)
    assert link is not None
    assert link.status is LinkStatus.VERIFIED


def test_main_pr_143709_explicit_key_from_kep_line(links: dict[int, Any]) -> None:
    link = best(links, 143709)
    assert link is not None
    assert (link.method, link.status) == (LinkMethod.EXPLICIT_KEY, LinkStatus.VERIFIED)
    assert link.evidence["where"] in {"kep_line", "implements"}


def test_related_issue_section_counts_as_explicit(links: dict[int, Any]) -> None:
    link = best(links, 143445)
    assert link is not None
    assert link.method is LinkMethod.EXPLICIT_KEY
    assert link.evidence["where"] == "related_issues_section"


def test_passing_mention_143644_stays_suggested(links: dict[int, Any]) -> None:
    """CLAUDE.md section 11: #143644 mentions #6395 only "as discussed in"."""
    link = best(links, 143644)
    assert link is not None
    assert (link.method, link.status) == (LinkMethod.EXPLICIT_KEY, LinkStatus.SUGGESTED)
    assert link.confidence < best(links, 143709).confidence  # type: ignore[union-attr]
    assert "as discussed in" in link.evidence["snippet"]


def test_143644_mentions_two_keps(links: dict[int, Any]) -> None:
    assert best(links, 143644, K1432) is not None
    assert best(links, 143709, K1432) is None


def test_feature_gate_links_main_pr(index: LinkIndex) -> None:
    node = next(n for n in load_json("prs_6395.json") if n["number"] == 143709)
    gates = [
        c for c in link_pull_request(pr_info(node), index) if c.method is LinkMethod.FEATURE_GATE
    ]
    assert len(gates) == 1
    assert gates[0].status is LinkStatus.VERIFIED
    assert gates[0].evidence["feature_gate"] == "DynamicNodeLocalEphemeralVolumes"


def test_sig_overlap_is_recorded_as_evidence(links: dict[int, Any]) -> None:
    link = best(links, 143709)
    assert link is not None
    assert set(link.evidence["sig_overlap"]) >= {"sig/node", "sig/storage"}


def test_tracking_list_parsed_from_issue_description() -> None:
    tracked = tracked_pull_requests(load_json("issue_6395.json")["body"])
    kk = sorted(n for repo, n in tracked if repo == "kubernetes/kubernetes")
    assert kk == [143442, 143445, 143474, 143522, 143709]
    assert ("kubernetes/enhancements", 6421) in tracked  # the KEP PR itself


# ---------------------------------------------------------------- edge cases


def _pr(title: str = "x", body: str = "", number: int = 1) -> PullRequestInfo:
    return PullRequestInfo(
        key=f"kubernetes/kubernetes#{number}",
        repo="kubernetes/kubernetes",
        number=number,
        title=title,
        body=body,
    )


def test_title_reference_is_strong() -> None:
    [ref] = find_kep_refs("[KEP-6395] add API", "")
    assert (ref.number, ref.where, ref.strong) == (6395, Where.TITLE, True)


def test_html_comments_are_ignored() -> None:
    body = "<!-- e.g. KEP: https://github.com/kubernetes/enhancements/issues/6395 -->"
    assert find_kep_refs("x", body) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("KEP-63951", [63951]),
        ("see kubernetes/enhancements#6395.", [6395]),
        ("keps/sig-node/6395-thing/README.md", [6395]),
        ("https://github.com/kubernetes/enhancements/issues/63950", [63950]),
        ("KEP 6395 and KEP-6395 again", [6395]),
        ("no references here, PR #143709", []),
    ],
)
def test_number_extraction(text: str, expected: list[int]) -> None:
    assert numbers_in(text) == expected


def test_reference_to_kep_outside_release_creates_no_link(index: LinkIndex) -> None:
    body = "KEP: https://github.com/kubernetes/enhancements/issues/9"
    assert link_pull_request(_pr(body=body), index) == []


def test_unlinked_pr_has_no_candidates(index: LinkIndex) -> None:
    assert link_pull_request(_pr(title="fix typo", body="small cleanup"), index) == []


def test_shared_feature_gate_is_only_suggested() -> None:
    items = [WorkItemInfo(key=f"k#{n}", number=n, feature_flags=("SharedGate",)) for n in (1, 2)]
    candidates = link_pull_request(_pr(body="behind the SharedGate gate"), LinkIndex.build(items))
    assert {(c.work_item_key, c.status) for c in candidates} == {
        ("k#1", LinkStatus.SUGGESTED),
        ("k#2", LinkStatus.SUGGESTED),
    }


def test_gate_match_is_whole_word() -> None:
    items = [WorkItemInfo(key="k#1", number=1, feature_flags=("Foo",))]
    assert link_pull_request(_pr(body="FooBar enabled"), LinkIndex.build(items)) == []


def test_verified_beats_suggested_regardless_of_rank() -> None:
    weak = LinkCandidate("p", "w", LinkMethod.EXPLICIT_KEY, LinkStatus.SUGGESTED, Decimal("0.5"))
    strong = LinkCandidate(
        "p", "w", LinkMethod.TRACKING_ISSUE_LINK, LinkStatus.VERIFIED, Decimal("0.9")
    )
    assert best_links([weak, strong])[("p", "w")] is strong
    assert best_links([strong, weak])[("p", "w")] is strong


def test_gate_matching_prefers_longest_and_handles_many_gates() -> None:
    items = [
        WorkItemInfo(key="k#1", number=1, feature_flags=("Foo",)),
        WorkItemInfo(key="k#2", number=2, feature_flags=("FooBar",)),
    ]
    index = LinkIndex.build(items)
    assert index.gates_in("enable FooBar and Foo") == ["Foo", "FooBar"]
    assert index.gates_in("FooBarBaz") == []
    assert LinkIndex.build([]).gates_in("anything") == []
