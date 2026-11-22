"""Jira-key linking for company-shaped plans (e.g. KAFKA-21181 in PR text).

Strong: key in title, or on a ``Jira:`` / ``Issue:`` / ``Fixes:`` line.
Passing: key appears elsewhere in the body → suggested only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from linker.methods import LinkMethod, LinkStatus
from linker.rules import CONFIDENCE, LinkCandidate, LinkIndex, PullRequestInfo, WorkItemInfo

_KEY = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_STRONG_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\**jira\**|\**issue\**|\**fixes\**|\**closes\**)\s*:",
    re.I,
)


def _keys_in(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in _KEY.finditer(text):
        seen.setdefault(match.group(1).upper(), None)
    return list(seen)


def _strong_keys(title: str, body: str) -> set[str]:
    found = set(_keys_in(title))
    for line in body.splitlines():
        if _STRONG_LINE.match(line):
            found.update(_keys_in(line))
    return found


def _work_item_for(index: LinkIndex, jira_key: str) -> WorkItemInfo | None:
    """Match by external key (``KAFKA-21181``) against ``WorkItemInfo.key``."""
    needle = jira_key.upper()
    for item in index.by_number.values():
        external = item.key.rsplit("/", 1)[-1].upper()
        if external == needle or item.key.upper().endswith(needle):
            return item
    return None


class JiraKeyPack:
    """Link PRs that mention Jira issue keys."""

    name = "jira_key"

    def link(
        self,
        pull_request: PullRequestInfo,
        index: LinkIndex,
    ) -> Sequence[LinkCandidate]:
        """Emit explicit_key candidates for recognized Jira keys."""
        strong = _strong_keys(pull_request.title, pull_request.body)
        all_keys = list(dict.fromkeys(_keys_in(pull_request.title) + _keys_in(pull_request.body)))
        out: list[LinkCandidate] = []
        for key in all_keys:
            item = _work_item_for(index, key)
            if item is None:
                continue
            status = LinkStatus.VERIFIED if key in strong else LinkStatus.SUGGESTED
            method = LinkMethod.EXPLICIT_KEY
            out.append(
                LinkCandidate(
                    pull_request_key=pull_request.key,
                    work_item_key=item.key,
                    method=method,
                    status=status,
                    confidence=CONFIDENCE[(method, status)],
                    evidence={
                        "jira_key": key,
                        "where": "title_or_issue_line" if key in strong else "body",
                        "snippet": key,
                    },
                )
            )
        return out
