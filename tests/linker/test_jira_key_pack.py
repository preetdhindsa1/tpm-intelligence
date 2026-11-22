"""Jira-key link pack for company-shaped planning tickets."""

from __future__ import annotations

from linker.methods import LinkMethod, LinkStatus
from linker.packs import get_pack
from linker.rules import LinkIndex, PullRequestInfo, WorkItemInfo, best_links


def test_title_jira_key_is_verified() -> None:
    index = LinkIndex.build(
        [WorkItemInfo(key="KAFKA-21181", number=21181, description="status drift")]
    )
    pr = PullRequestInfo(
        key="apache/kafka#1",
        repo="apache/kafka",
        number=1,
        title="KAFKA-21181 fix metadata",
        body="implementation",
    )
    link = best_links(list(get_pack("jira_key").link(pr, index)))[("apache/kafka#1", "KAFKA-21181")]
    assert (link.method, link.status) == (LinkMethod.EXPLICIT_KEY, LinkStatus.VERIFIED)


def test_passing_body_mention_stays_suggested() -> None:
    index = LinkIndex.build([WorkItemInfo(key="KAFKA-19831", number=19831)])
    pr = PullRequestInfo(
        key="apache/kafka#2",
        repo="apache/kafka",
        number=2,
        title="misc cleanup",
        body="as discussed for KAFKA-19831 last week",
    )
    link = best_links(list(get_pack("jira_key").link(pr, index)))[("apache/kafka#2", "KAFKA-19831")]
    assert link.status is LinkStatus.SUGGESTED


def test_fixes_line_is_strong() -> None:
    index = LinkIndex.build([WorkItemInfo(key="KAFKA-17789", number=17789)])
    pr = PullRequestInfo(
        key="apache/kafka#3",
        repo="apache/kafka",
        number=3,
        title="follow-up",
        body="Fixes: KAFKA-17789\n\nDetails here.",
    )
    link = best_links(list(get_pack("jira_key").link(pr, index)))[("apache/kafka#3", "KAFKA-17789")]
    assert link.status is LinkStatus.VERIFIED
