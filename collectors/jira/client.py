"""Jira REST API v2 client (anonymous reads of public Apache Jira; CLAUDE.md section 7).

API only, never web pages. Apache rate-limits automated tools with HTTP 429 (about two
minutes); the shared HttpClient waits that out, and this client also spaces requests at
least ``min_interval_s`` apart so a sync stays polite.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from collectors.http import HttpClient, RetryPolicy

ISSUE_FIELDS = (
    "summary,status,issuetype,fixVersions,labels,parent,description,created,updated,"
    "components,issuelinks,subtasks,resolution,resolutiondate"
)


class JiraClient:
    """Reads issues, their full changelogs, remote links and project versions."""

    def __init__(
        self,
        http: HttpClient,
        *,
        min_interval_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._min_interval_s = min_interval_s
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None
        self.requests = 0
        self.full_changelogs = 0  # issues re-fetched because search truncated the changelog

    @classmethod
    def from_base_url(cls, base_url: str, **kwargs: Any) -> JiraClient:
        """``https://issues.apache.org/jira`` -> a client for its ``/rest/api/2``."""
        http = HttpClient(
            f"{base_url.rstrip('/')}/rest/api/2",
            headers={"Accept": "application/json", "User-Agent": "tpm-intelligence-jira"},
            policy=kwargs.pop("policy", RetryPolicy()),
            **{k: kwargs.pop(k) for k in list(kwargs) if k in ("transport", "instrument")},
        )
        return cls(http, **kwargs)

    def close(self) -> None:
        """Release connections."""
        self._http.close()

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        if self._last is not None:
            wait = self._min_interval_s - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        try:
            return self._http.get(path, params=dict(params or {})).json()
        finally:
            self._last = self._clock()
            self.requests += 1

    def versions(self, project_key: str) -> list[dict[str, Any]]:
        """Every version (release) of a project, with released flags and dates."""
        result: list[dict[str, Any]] = self._get(f"/project/{project_key}/versions")
        return result

    def search(self, jql: str, *, page_size: int = 50) -> Iterator[dict[str, Any]]:
        """Issues matching ``jql`` with their changelogs, completed when Jira truncates them."""
        start = 0
        while True:
            page = self._get(
                "/search",
                {
                    "jql": jql,
                    "startAt": start,
                    "maxResults": page_size,
                    "fields": ISSUE_FIELDS,
                    "expand": "changelog",
                },
            )
            issues: Sequence[dict[str, Any]] = page.get("issues", [])
            for issue in issues:
                log = issue.get("changelog", {})
                if log.get("total", 0) > len(log.get("histories", [])):
                    issue = self.issue(issue["key"])  # search results cap the changelog
                    self.full_changelogs += 1
                yield issue
            start += len(issues)
            if not issues or start >= page.get("total", 0):
                return

    def issue(self, key: str) -> dict[str, Any]:
        """One issue with its full changelog."""
        result: dict[str, Any] = self._get(
            f"/issue/{key}", {"fields": ISSUE_FIELDS, "expand": "changelog"}
        )
        return result

    def remote_links(self, key: str) -> list[dict[str, Any]]:
        """Remote links (e.g. GitHub pull requests) of an issue."""
        result: list[dict[str, Any]] = self._get(f"/issue/{key}/remotelink")
        return result
