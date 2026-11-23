"""github_issue link pack (ADR-0020): GitHub's closing keywords verify a link; a bare
mention only suggests one (the same rule as #143644 for KEPs, CLAUDE.md section 11)."""

from __future__ import annotations

from linker.methods import LinkMethod, LinkStatus
from linker.packs import get_pack
from linker.packs.github_issue import references
from linker.rules import LinkIndex, PullRequestInfo, WorkItemInfo

REPO = "preetdhindsa1/program-demo-team"
ISSUES = LinkIndex.build([WorkItemInfo(key=f"{REPO}#{n}", number=n) for n in (3, 12)])


def pr(title: str, body: str = "", number: int = 40, repo: str = REPO) -> PullRequestInfo:
    return PullRequestInfo(key=f"{repo}#{number}", repo=repo, number=number, title=title, body=body)


def links(p: PullRequestInfo) -> dict[str, LinkStatus]:
    return {c.work_item_key: c.status for c in get_pack("github_issue").link(p, ISSUES)}


def test_closing_keywords_verify() -> None:
    for body in (
        "Fixes #12",
        "closes #12",
        "Resolved: #12",
        f"Closes {REPO}#12",
        f"fixes https://github.com/{REPO}/issues/12",
        "Feature: #12",
        "- **Issue:** #12",
    ):
        assert links(pr("Add exporter", body)) == {f"{REPO}#12": LinkStatus.VERIFIED}, body


def test_bare_mention_is_only_suggested() -> None:
    got = links(pr("Add exporter", "As discussed in #3, this also touches the parser."))
    assert got == {f"{REPO}#3": LinkStatus.SUGGESTED}


def test_closing_and_mention_together() -> None:
    got = links(pr("Fix #12 crash", "Related to #3"))
    assert got == {f"{REPO}#12": LinkStatus.VERIFIED, f"{REPO}#3": LinkStatus.SUGGESTED}


def test_unknown_issues_comments_and_other_repos_are_ignored() -> None:
    assert links(pr("Fixes #999")) == {}
    assert links(pr("Tidy", "<!-- Fixes #12 -->")) == {}
    # Short #12 in another repo's PR means that repo's issue 12, not ours.
    assert links(pr("Fixes #12", repo="someone/else")) == {}
    assert links(pr("Fixes #120")) == {}  # 12 is not 120


def test_method_and_references() -> None:
    [c] = get_pack("github_issue").link(pr("x", "Fixes #12"), ISSUES)
    assert c.method is LinkMethod.EXPLICIT_KEY
    strong, named = references(pr("x", "Fixes #12, see #3"))
    assert strong == {f"{REPO.lower()}#12"}
    assert named == {f"{REPO.lower()}#12", f"{REPO.lower()}#3"}
