"""Link PRs to planning issues on GitHub with GitHub's own closing keywords (ADR-0020).

For team repos that plan in GitHub issues (the demo team). Pure, no I/O.

* **Strong (verified, explicit_key):** a closing keyword followed by the issue
  (``Fixes #12``, ``closes owner/repo#12``, ``Resolves https://github.com/owner/repo/issues/12``)
  or a ``Feature: #12`` / ``Issue: #12`` line. GitHub itself links these.
* **Passing (suggested):** a bare ``#12`` or issue URL anywhere else in the title or body.

A short ``#12`` means an issue in the PR's own repository, as on GitHub.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from linker.methods import LinkMethod, LinkStatus
from linker.rules import CONFIDENCE, LinkCandidate, LinkIndex, PullRequestInfo, WorkItemInfo

_ISSUE = (
    r"(?:(?P<repo>[\w.-]+/[\w.-]+)#(?P<n1>\d+)"
    r"|https://github\.com/(?P<urlrepo>[\w.-]+/[\w.-]+)/issues/(?P<n2>\d+)"
    r"|#(?P<n3>\d+))(?!\d)"
)
_CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+" + _ISSUE, re.IGNORECASE)
# "Feature: #12", "**Issue:** #12", "- **Feature**: #12"
_LINE = re.compile(r"^\s*(?:[-*]\s*)?\**(?:feature|issue)(?:\**\s*:|:\**)\s*" + _ISSUE, re.I | re.M)
_ANY = re.compile(_ISSUE)
_COMMENTS = re.compile(r"<!--.*?-->", re.S)


def _key(match: re.Match[str], pr_repo: str) -> str:
    repo = match.group("repo") or match.group("urlrepo") or pr_repo
    number = match.group("n1") or match.group("n2") or match.group("n3")
    return f"{repo.lower()}#{int(number)}"


def references(pr: PullRequestInfo) -> tuple[set[str], set[str]]:
    """(strong, all) issue keys a PR names, as lower-case ``owner/repo#N``."""
    text = _COMMENTS.sub("", f"{pr.title}\n{pr.body}")
    strong = {_key(m, pr.repo) for m in _CLOSING.finditer(text)}
    strong |= {_key(m, pr.repo) for m in _LINE.finditer(text)}
    return strong, strong | {_key(m, pr.repo) for m in _ANY.finditer(text)}


class GitHubIssuePack:
    """``explicit_key`` links from closing keywords; bare mentions stay suggested."""

    name = "github_issue"

    def link(self, pull_request: PullRequestInfo, index: LinkIndex) -> Sequence[LinkCandidate]:
        """Candidates for every indexed planning issue the PR names."""
        items: dict[str, WorkItemInfo] = {i.key.lower(): i for i in index.by_number.values()}
        strong, named = references(pull_request)
        out: list[LinkCandidate] = []
        for key in sorted(named):
            item = items.get(key)
            if item is None or item.key == pull_request.key:
                continue
            verified = key in strong
            method = LinkMethod.EXPLICIT_KEY
            status = LinkStatus.VERIFIED if verified else LinkStatus.SUGGESTED
            out.append(
                LinkCandidate(
                    pull_request_key=pull_request.key,
                    work_item_key=item.key,
                    method=method,
                    status=status,
                    confidence=CONFIDENCE[(method, status)],
                    evidence={
                        "issue": item.key,
                        "where": "closing_keyword_or_feature_line" if verified else "mention",
                    },
                )
            )
        return out
