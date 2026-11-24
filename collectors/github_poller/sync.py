"""Poll GitHub for one Kubernetes release and publish normalized events.

Streams (each has its own cursor in ``sync_cursors``):

* ``github:<enh repo>:issues:<release>``: enhancement issues updated since the cursor (or
  the cycle start). Each issue's GraphQL timeline (full history; REST caps at ~300 events)
  decides whether it is or ever was in the release milestone, so removed items such as
  #6395 (demilestoned 2026-11-17) are kept.
* ``github:<code repo>:prs:<release>``: every PR in the window, via GraphQL search. Backfill
  covers PRs *created* or *merged* between cycle start and release (or now). Incremental
  runs use ``updated:>=cursor``. Unlinked PRs are included on purpose: they are reviewer
  and CI load (CLAUDE.md section 6). PRs named in an issue's tracking list but outside the
  window are fetched by number.

Teams that plan in Jira (ADR-0018) run in **code-only** mode: ``enhancements_repo`` is
None, no planning issues or release event are published (the Jira collector owns both),
and the PR window is passed in from the Jira release dates.

Tracing: one root span per synced item (issue or PR), linked to the run span, so each
trace follows an item from the collector through the queue to the worker without one
enormous trace per backfill.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Link

from collectors.github_poller import normalize
from collectors.github_poller.calendar import Calendar, ReleaseDates
from collectors.github_poller.client import GitHubClient
from collectors.github_poller.queries import (
    ISSUE_TIMELINE,
    MORE_COMMENTS,
    MORE_REVIEWS,
    prs_by_number_query,
    search_prs_query,
)
from pipeline.events import NormalizedEvent
from pipeline.queue import EventPublisher
from pipeline.store.cursors import CursorStore

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

SEARCH_RESULT_CAP = 1000  # GitHub search returns at most 1000 results per query
# Backfill scans issues updated from this long before cycle start: an issue milestoned
# early and untouched since would otherwise be missed.
ISSUE_LOOKBACK = timedelta(days=90)
_PR_URL = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)")


@dataclass
class SyncStats:
    """What one run did (logged and returned for tests)."""

    issues_scanned: int = 0
    issues_in_release: int = 0
    prs_synced: int = 0
    tracked_prs_fetched_by_number: int = 0
    tracked_prs_other_repos: int = 0
    spec_parse_errors: int = 0
    events_published: int = 0
    failed_streams: list[str] = field(default_factory=list)


@dataclass
class GitHubPoller:
    """Syncs one release. Construct per run."""

    gh: GitHubClient
    publisher: EventPublisher
    cursors: CursorStore
    calendar: Calendar | None
    release_name: str
    enhancements_repo: str | None = "kubernetes/enhancements"
    code_repo: str = "kubernetes/kubernetes"
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    # PRs per search page. Each PR brings up to 100 comments with their text (Prow bot
    # comments are long); 50 per page made GitHub time out (HTTP 504) and truncate JSON.
    page_size: int = 10
    cursor_overlap: timedelta = timedelta(minutes=10)
    stats: SyncStats = field(default_factory=SyncStats)
    _tracked_prs: set[tuple[str, int]] = field(default_factory=set)
    _kep_paths: dict[int, str] | None = None
    # Kubernetes keeps a kep.yaml per enhancement; other planning repos have no such specs
    # (asking for one failed every run for this project, issue #11).
    read_kep_specs: bool = True
    # Code-only mode: (cycle start, release day or None while unset).
    window: tuple[datetime, datetime | None] | None = None
    # Ask GitHub for file paths, line counts and commit messages (development lab only).
    lane_fields: bool = False

    @property
    def release(self) -> ReleaseDates:
        """Calendar entry for this release."""
        if self.calendar is None:
            raise ValueError("no calendar: code-only poller")
        return self.calendar.get(self.release_name)

    @property
    def _planning(self) -> str:
        if self.enhancements_repo is None:
            raise ValueError("code-only poller has no planning repo")
        return self.enhancements_repo

    @property
    def release_project(self) -> str:
        """Release-key prefix from the calendar."""
        if self.calendar is None:
            raise ValueError("no calendar: code-only poller")
        return self.calendar.project

    def _window(self) -> tuple[datetime, datetime]:
        """PR window: cycle start to release day, capped at now."""
        if self.window is not None:
            start, end = self.window
            return start, min(self.now(), end) if end else self.now()
        return self.release.cycle_start, min(self.now(), self.release.release)

    @property
    def issues_stream(self) -> str:
        """Cursor key for enhancement issues."""
        return f"github:{self.enhancements_repo}:issues:{self.release_name}"

    @property
    def prs_stream(self) -> str:
        """Cursor key for pull requests."""
        return f"github:{self.code_repo}:prs:{self.release_name}"

    # ------------------------------------------------------------ entry point

    def run(self, *, backfill: bool = False) -> SyncStats:
        """Sync everything for the release. ``backfill`` ignores stored cursors."""
        with tracer.start_as_current_span(
            "github_poller.run",
            attributes={"tpm.release": self.release_name, "tpm.backfill": backfill},
        ):
            if self.enhancements_repo is not None and self.calendar is not None:
                self._publish(
                    normalize.release_event(self.calendar.project, self.release, self.now())
                )
                self._guarded(self.issues_stream, lambda: self.sync_enhancements(backfill=backfill))
            self._guarded(self.prs_stream, lambda: self.sync_pull_requests(backfill=backfill))
        logger.info("poll finished", extra={"stats": self.stats.__dict__})
        return self.stats

    def _guarded(self, stream: str, fn: Callable[[], str | None]) -> None:
        """Run one stream; on success store its cursor, on failure count it and continue."""
        started = self.now()
        try:
            cursor = fn()
        except Exception as exc:
            failures = self.cursors.record_failure(stream, f"{type(exc).__name__}: {exc}", started)
            self.stats.failed_streams.append(stream)
            logger.exception(
                "stream failed", extra={"stream": stream, "consecutive_failures": failures}
            )
            return
        self.cursors.record_success(stream, cursor, started)

    def _issues_since(self, backfill: bool) -> datetime:
        cursor = None if backfill else self.cursors.get(self.issues_stream)
        if cursor:
            return normalize.parse_ts(cursor) - self.cursor_overlap
        return self.release.cycle_start - ISSUE_LOOKBACK

    def _publish(self, event: NormalizedEvent) -> None:
        self.publisher.publish(event)
        self.stats.events_published += 1

    def _item_span(self, name: str, **attributes: Any) -> Any:
        """New root span per item, linked to the current (run) span."""
        run_ctx = trace.get_current_span().get_span_context()
        return tracer.start_as_current_span(
            name,
            context=otel_context.Context(),
            links=[Link(run_ctx)] if run_ctx.is_valid else [],
            attributes=attributes,
        )

    # ------------------------------------------------------------ enhancements

    def sync_enhancements(self, *, backfill: bool = False) -> str | None:
        """Publish issue snapshots, milestone/label history and KEP metadata."""
        since = self._issues_since(backfill)
        observed = self.now()
        max_updated: str | None = self.cursors.get(self.issues_stream) if not backfill else None
        repo = self._planning
        issues = self.gh.paginate(
            f"/repos/{repo}/issues",
            {"state": "all", "since": since.isoformat(), "sort": "updated", "direction": "asc"},
        )
        for issue in issues:
            if normalize.is_pull_request(issue):
                continue
            self.stats.issues_scanned += 1
            max_updated = max(filter(None, [max_updated, issue["updated_at"]]))
            number = issue["number"]
            events = self.issue_timeline(number)
            if not normalize.issue_in_release(issue, events, self.release_name):
                continue
            self.stats.issues_in_release += 1
            with self._item_span("github_poller.issue", **{"tpm.work_item": f"{repo}#{number}"}):
                self._sync_issue(issue, events, observed)
        return max_updated

    def _sync_issue(self, issue: dict[str, Any], events: list[Any], observed: datetime) -> None:
        repo, number, project = self._planning, issue["number"], self.release_project
        self._publish(
            normalize.issue_snapshot(issue, repo=repo, project=project, observed_at=observed)
        )
        for event in normalize.issue_history(
            events, repo=repo, number=number, project=project, observed_at=observed
        ):
            self._publish(event)
        path = self.kep_paths().get(number) if self.read_kep_specs else None
        if path:
            text = self.gh.get_text(f"/repos/{repo}/contents/{path}")
            try:
                spec = normalize.kep_spec(
                    text,
                    path=path,
                    repo=repo,
                    number=number,
                    project=project,
                    observed_at=observed,
                    occurred_at=observed,
                )
            except normalize.SpecParseError as exc:
                # Bad source data for one item must not stop the stream (HTTP errors still do).
                self.stats.spec_parse_errors += 1
                logger.warning(
                    "kep.yaml not parseable; skipping spec",
                    extra={"work_item": f"{repo}#{number}", "error": str(exc)},
                )
            else:
                self._publish(spec)
        for pr_repo, pr_number in _PR_URL.findall(issue.get("body") or ""):
            self._tracked_prs.add((pr_repo, int(pr_number)))

    def issue_timeline(self, number: int) -> list[dict[str, Any]]:
        """Full milestone/label/close history via GraphQL (REST caps at ~300 events)."""
        return fetch_issue_timeline(self.gh, self._planning, number)

    def kep_paths(self) -> dict[int, str]:
        """KEP number -> kep.yaml path (one recursive tree call per run)."""
        if self._kep_paths is None:
            tree = self.gh.get_json(f"/repos/{self._planning}/git/trees/master", {"recursive": "1"})
            if tree.get("truncated"):
                logger.warning("git tree listing truncated; some kep.yaml files may be missed")
            self._kep_paths = normalize.kep_paths(tree.get("tree", []))
        return self._kep_paths

    # ------------------------------------------------------------ pull requests

    def sync_pull_requests(self, *, backfill: bool = False) -> str | None:
        """Publish PRs in the window plus tracked PRs fetched by number."""
        cursor = None if backfill else self.cursors.get(self.prs_stream)
        observed = self.now()
        base = f"repo:{self.code_repo} is:pr"
        if cursor:
            since = normalize.parse_ts(cursor) - self.cursor_overlap
            queries = [f"{base} updated:>={_q(since)}"]
            ranges: list[tuple[str, datetime, datetime]] = []
        else:
            start, end = self._window()
            queries = []
            ranges = [(f"{base} created", start, end), (f"{base} merged", start, end)]

        seen: set[int] = set()
        max_updated = cursor
        nodes = [n for q in queries for n in self._search(q)]
        nodes += [n for prefix, a, b in ranges for n in self._search_range(prefix, a, b)]
        for node in nodes:
            if node["number"] in seen:
                continue
            seen.add(node["number"])
            max_updated = max(filter(None, [max_updated, node["updatedAt"]]))
            self._sync_pr(node, observed)

        owner, name = self.code_repo.split("/")
        missing = sorted(n for r, n in self._tracked_prs if r == self.code_repo and n not in seen)
        self.stats.tracked_prs_other_repos = sum(
            1 for r, _ in self._tracked_prs if r != self.code_repo
        )
        for chunk in _chunks(missing, 10):
            data = self.gh.graphql(
                prs_by_number_query(owner, name, chunk, lane=self.lane_fields),
                allow_not_found=True,
            )
            for n in chunk:
                node = data["repository"].get(f"pr{n}")
                if node:
                    self.stats.tracked_prs_fetched_by_number += 1
                    self._sync_pr(node, observed)
        return max_updated or _q(self._window()[0])

    def _sync_pr(self, node: dict[str, Any], observed: datetime) -> None:
        key = f"{node['repository']['nameWithOwner']}#{node['number']}"
        with self._item_span("github_poller.pull_request", **{"tpm.pull_request": key}):
            self._complete_reviews(node)
            self._complete_comments(node)
            for event in normalize.pull_request_events(node, observed_at=observed):
                self._publish(event)
        self.stats.prs_synced += 1

    def _complete_reviews(self, node: dict[str, Any]) -> None:
        """Fetch remaining review pages in place (PRs with 100+ review records)."""
        page = node["reviews"]["pageInfo"]
        owner, name = node["repository"]["nameWithOwner"].split("/")
        while page.get("hasNextPage"):
            data = self.gh.graphql(
                MORE_REVIEWS,
                {
                    "owner": owner,
                    "name": name,
                    "number": node["number"],
                    "after": page["endCursor"],
                },
            )
            reviews = data["repository"]["pullRequest"]["reviews"]
            node["reviews"]["nodes"].extend(reviews["nodes"])
            page = reviews["pageInfo"]

    def _complete_comments(self, node: dict[str, Any]) -> None:
        """Fetch remaining comment pages in place (PRs with 100+ comments)."""
        comments = node.get("comments")
        if not comments:
            return
        page = comments["pageInfo"]
        owner, name = node["repository"]["nameWithOwner"].split("/")
        while page.get("hasNextPage"):
            data = self.gh.graphql(
                MORE_COMMENTS,
                {
                    "owner": owner,
                    "name": name,
                    "number": node["number"],
                    "after": page["endCursor"],
                },
            )
            more = data["repository"]["pullRequest"]["comments"]
            comments["nodes"].extend(more["nodes"])
            page = more["pageInfo"]

    def _search(self, query: str) -> Iterator[dict[str, Any]]:
        after: str | None = None
        while True:
            data = self.gh.graphql(
                search_prs_query(lane=self.lane_fields),
                {"q": query, "first": self.page_size, "after": after},
            )
            result = data["search"]
            yield from (n for n in result["nodes"] if n and "number" in n)
            if not result["pageInfo"]["hasNextPage"]:
                return
            after = result["pageInfo"]["endCursor"]

    def _search_range(
        self, prefix: str, start: datetime, end: datetime
    ) -> Iterator[dict[str, Any]]:
        """Search ``prefix:start..end``, halving the range while it exceeds the 1000 cap."""
        query = f"{prefix}:{_q(start)}..{_q(end)}"
        probe = self.gh.graphql(
            search_prs_query(lane=self.lane_fields), {"q": query, "first": 1, "after": None}
        )
        count = int(probe["search"]["issueCount"])
        if count > SEARCH_RESULT_CAP and end - start > timedelta(minutes=1):
            mid = start + (end - start) / 2
            yield from self._search_range(prefix, start, mid)
            yield from self._search_range(prefix, mid, end)
            return
        if count > SEARCH_RESULT_CAP:
            logger.warning("search still over cap at minimum range", extra={"query": query})
        yield from self._search(query)


def fetch_issue_timeline(gh: GitHubClient, repo: str, number: int) -> list[dict[str, Any]]:
    """An issue's full milestone/label/close history via GraphQL, in issue-event shape.

    Shared with the webhook receiver (ADR-0020) so both produce the same event IDs: the
    IDs come from GraphQL timeline node IDs, which webhook payloads do not carry.
    """
    owner, name = repo.split("/")
    nodes: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        data = gh.graphql(
            ISSUE_TIMELINE, {"owner": owner, "name": name, "number": number, "after": after}
        )
        items = data["repository"]["issue"]["timelineItems"]
        nodes.extend(items["nodes"])
        if not items["pageInfo"]["hasNextPage"]:
            return normalize.timeline_to_events(nodes)
        after = items["pageInfo"]["endCursor"]


def _q(ts: datetime) -> str:
    """Timestamp formatted for GitHub search qualifiers."""
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chunks(items: list[int], size: int) -> Iterator[list[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
