"""Poller end to end against a fake GitHub API serving the real #6395 fixtures."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from collectors.github_poller.calendar import load_calendar
from collectors.github_poller.client import GitHubClient
from collectors.github_poller.sync import GitHubPoller
from collectors.http import HttpClient, RetryPolicy
from pipeline.events import NormalizedEvent
from pipeline.memory import InMemoryTransport
from pipeline.queue import EVENTS_TOPIC, EventPublisher
from pipeline.store.cursors import InMemoryCursorStore
from tests.collectors.conftest import load_json, load_text

NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)
ENH = "/repos/kubernetes/enhancements"
KEP_PATH = "keps/sig-storage/6395-dynamic-node-local-ephemeral-volumes/kep.yaml"


@dataclass
class FakeGitHub:
    """Routes REST and GraphQL calls to fixtures; records what was asked."""

    search_hits: list[int] = field(default_factory=lambda: [143709, 143644])
    fail_search: bool | str = False  # PR search only: True/"502", "429" (long wait), "timeout"
    search_count: Any = None  # callable(query) -> issueCount, for split tests
    requests: list[httpx.Request] = field(default_factory=list)
    graphql_queries: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.prs = {n["number"]: n for n in load_json("prs_6395.json")}
        issue = load_json("issue_6395.json")
        self.issues = [
            {**issue, "milestone": None},  # as on 2026-11-18: removed at Code Freeze
            {
                "number": 6000,
                "title": "Unrelated",
                "state": "open",
                "labels": [],
                "milestone": {"title": "v1.37"},
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": "2026-10-01T00:00:00Z",
                "body": "",
            },
            {"number": 6421, "pull_request": {}, "updated_at": "2026-10-02T00:00:00Z"},
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/graphql":
            return self._graphql(json.loads(request.content))
        if path == f"{ENH}/issues":
            return httpx.Response(200, json=self.issues)
        if path == f"{ENH}/git/trees/master":
            return httpx.Response(200, json={"truncated": False, "tree": [{"path": KEP_PATH}]})
        if path == f"{ENH}/contents/{KEP_PATH}":
            return httpx.Response(200, text=load_text("kep_6395.yaml"))
        return httpx.Response(404, json={"message": f"no fixture for {path}"})

    def _graphql(self, body: dict[str, Any]) -> httpx.Response:
        query, variables = body["query"], body.get("variables", {})
        if self.fail_search and "query SearchPRs" in query:
            if self.fail_search == "timeout":
                raise httpx.ReadTimeout("search timed out")
            if self.fail_search == "429":
                return httpx.Response(429, headers={"retry-after": "99999"})
            return httpx.Response(502)
        self.graphql_queries.append(body)
        if "query IssueTimeline" in query:
            nodes = load_json("issue_6395_timeline.json") if variables["number"] == 6395 else []
            half = len(nodes) // 2
            if variables["after"] is None and half:  # two pages to exercise pagination
                return _data(_timeline(nodes[:half], {"hasNextPage": True, "endCursor": "c1"}))
            rest = nodes[half:] if variables["after"] else nodes
            return _data(_timeline(rest, {"hasNextPage": False, "endCursor": None}))
        if "query SearchPRs" in query:
            q = variables["q"]
            in_window = " created:" in q or "updated:" in q
            hits = [self.prs[n] for n in self.search_hits] if in_window else []
            count = self.search_count(q) if self.search_count else len(hits)
            nodes = hits[: variables["first"]]
            return _data(
                {
                    "search": {
                        "issueCount": count,
                        "nodes": nodes,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            )
        if "query PRsByNumber" in query:
            wanted = [int(n) for n in re.findall(r"pr(\d+): pullRequest", query)]
            body = {"data": {"repository": {f"pr{n}": self.prs.get(n) for n in wanted}}}
            missing = [n for n in wanted if n not in self.prs]
            if missing:  # what GitHub returns for a deleted / inaccessible PR
                body["errors"] = [
                    {"type": "NOT_FOUND", "message": f"pr{n} not found"} for n in missing
                ]
            return httpx.Response(200, json=body)
        return httpx.Response(400, json={"message": "unexpected query"})


def _timeline(nodes: list[Any], page: dict[str, Any]) -> dict[str, Any]:
    items = {"totalCount": len(nodes), "pageInfo": page, "nodes": nodes}
    return {"repository": {"issue": {"timelineItems": items}}}


def _data(data: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def make_poller(
    fake: FakeGitHub, cursors: InMemoryCursorStore | None = None, *, read_kep_specs: bool = True
) -> tuple[GitHubPoller, InMemoryTransport, InMemoryCursorStore]:
    http = HttpClient(
        "https://api.github.com",
        transport=httpx.MockTransport(fake),
        policy=RetryPolicy(max_attempts=2),
        sleep=lambda s: None,
        instrument=False,
    )
    transport, store = InMemoryTransport(), cursors or InMemoryCursorStore()
    poller = GitHubPoller(
        gh=GitHubClient(http),
        publisher=EventPublisher(transport),
        cursors=store,
        calendar=load_calendar(),
        release_name="v1.38",
        now=lambda: NOW,
        read_kep_specs=read_kep_specs,
    )
    return poller, transport, store


def published(transport: InMemoryTransport) -> list[NormalizedEvent]:
    return [
        NormalizedEvent.from_bytes(m.data) for m in transport.pull(EVENTS_TOPIC, "test", 100_000, 0)
    ]


def test_backfill_publishes_release_issue_history_spec_and_prs() -> None:
    fake = FakeGitHub()
    poller, transport, store = make_poller(fake)
    stats = poller.run(backfill=True)
    events = published(transport)
    by_type: dict[str, list[NormalizedEvent]] = {}
    for e in events:
        by_type.setdefault(e.event_type, []).append(e)

    assert stats.failed_streams == []
    assert stats.events_published == len(events)
    # Release from the calendar.
    [release] = by_type["release.observed"]
    assert release.subject.external_key == "kubernetes:v1.38"
    # #6395 kept although it has no milestone right now; #6000 (v1.37) and the PR dropped.
    assert (stats.issues_scanned, stats.issues_in_release) == (2, 1)
    assert {e.subject.external_key for e in by_type["work_item.observed"]} == {
        "kubernetes/enhancements#6395"
    }
    removals = [e for e in by_type["work_item.release_changed"] if e.payload.action == "removed"]
    assert [e.occurred_at.isoformat() for e in removals] == ["2026-11-17T12:05:57+00:00"]
    [spec] = by_type["work_item.spec_observed"]
    assert spec.payload.feature_flags == ("DynamicNodeLocalEphemeralVolumes",)
    # All six PRs: two from search, four from the issue's tracking list fetched by number.
    pr_keys = {e.subject.external_key for e in by_type["pull_request.observed"]}
    assert pr_keys == {
        f"kubernetes/kubernetes#{n}" for n in (143442, 143445, 143474, 143522, 143644, 143709)
    }
    assert stats.tracked_prs_fetched_by_number == 4
    assert len(by_type["pull_request.review_submitted"]) > 50
    # Cursors advanced to the newest updated_at seen.
    assert store.get(poller.issues_stream) == load_json("issue_6395.json")["updated_at"]
    assert store.get(poller.prs_stream) == max(fake.prs[n]["updatedAt"] for n in fake.search_hits)


def test_backfill_search_covers_created_and_merged_in_window() -> None:
    fake = FakeGitHub()
    poller, _, _ = make_poller(fake)
    poller.run(backfill=True)
    queries = {q["variables"]["q"] for q in fake.graphql_queries if "q" in q["variables"]}
    assert (
        "repo:kubernetes/kubernetes is:pr created:2026-08-31T00:00:00Z..2026-11-21T12:00:00Z"
        in queries
    )
    assert (
        "repo:kubernetes/kubernetes is:pr merged:2026-08-31T00:00:00Z..2026-11-21T12:00:00Z"
        in queries
    )


def test_issue_backfill_looks_back_before_cycle_start() -> None:
    fake = FakeGitHub()
    poller, _, _ = make_poller(fake)
    poller.run(backfill=True)
    [issues_req] = [r for r in fake.requests if r.url.path == f"{ENH}/issues"]
    since = datetime.fromisoformat(issues_req.url.params["since"])
    assert since == datetime(2026, 8, 31, tzinfo=UTC) - timedelta(days=90)


def test_incremental_run_starts_from_cursor_minus_overlap() -> None:
    fake = FakeGitHub()
    store = InMemoryCursorStore()
    poller, _, _ = make_poller(fake, store)
    poller.run(backfill=True)
    issues_cursor = store.get(poller.issues_stream)
    assert issues_cursor is not None

    fake2 = FakeGitHub()
    poller2, _, _ = make_poller(fake2, store)
    poller2.run()
    [issues_req] = [r for r in fake2.requests if r.url.path == f"{ENH}/issues"]
    expected = datetime.fromisoformat(issues_cursor.replace("Z", "+00:00")) - timedelta(minutes=10)
    assert datetime.fromisoformat(issues_req.url.params["since"]) == expected
    queries = [q["variables"]["q"] for q in fake2.graphql_queries if "q" in q["variables"]]
    assert queries
    assert all(" updated:>=" in q for q in queries)


def test_repolling_publishes_identical_event_ids() -> None:
    first, _, _ = make_poller(FakeGitHub())
    second, _, _ = make_poller(FakeGitHub())
    t1, t2 = first.publisher.transport, second.publisher.transport
    first.run(backfill=True)
    second.run(backfill=True)
    ids1 = {e.event_id for e in published(t1)}  # type: ignore[arg-type]
    ids2 = {e.event_id for e in published(t2)}  # type: ignore[arg-type]
    assert ids1 == ids2


def test_failed_stream_is_counted_and_others_still_run() -> None:
    fake = FakeGitHub(fail_search=True)
    store = InMemoryCursorStore()
    poller, _, _ = make_poller(fake, store)
    stats = poller.run(backfill=True)
    assert stats.failed_streams == [poller.prs_stream]
    assert store.failures[poller.prs_stream] == 1
    assert store.failures[poller.issues_stream] == 0
    assert stats.issues_in_release == 1

    poller2, _, _ = make_poller(FakeGitHub(fail_search=True), store)
    poller2.run(backfill=True)
    assert store.failures[poller.prs_stream] == 2  # "2 failed polls in a row" alert input


@pytest.mark.parametrize("failure", ["502", "429", "timeout"])
def test_every_failure_keeps_the_cursor_and_the_data(failure: str) -> None:
    """GitHub down, rate-limited too long, or timing out (ADR-0036): the stream's cursor
    stays, the failure is counted, and the other stream still syncs and publishes."""
    store = InMemoryCursorStore()
    first, _, _ = make_poller(FakeGitHub(), store)
    first.run(backfill=True)
    before = store.cursors[first.prs_stream]
    poller, transport, _ = make_poller(FakeGitHub(fail_search=failure), store)
    stats = poller.run()
    assert stats.failed_streams == [poller.prs_stream]
    assert store.cursors[poller.prs_stream] == before
    assert store.failures[poller.prs_stream] == 1
    assert published(transport)  # the issues stream still ran
    [prs] = [h for h in store.health() if h.stream == poller.prs_stream]
    assert prs.consecutive_failures == 1
    assert prs.last_success_at is not None  # the earlier success is kept for freshness


def test_search_range_is_split_while_over_1000_results() -> None:
    def count(q: str) -> int:
        start, end = re.search(r":(\S+)\.\.(\S+)$", q).groups()  # type: ignore[union-attr]
        span = datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(
            start.replace("Z", "+00:00")
        )
        return 1500 if span > timedelta(days=30) else 400

    fake = FakeGitHub(search_count=count)
    poller, _, _ = make_poller(fake)
    poller.run(backfill=True)
    leaves = {
        q["variables"]["q"]
        for q in fake.graphql_queries
        if " created:" in q["variables"].get("q", "") and q["variables"]["first"] > 1
    }
    assert len(leaves) > 1  # the 82-day window was split
    assert all(count(q) <= 1000 for q in leaves)


def test_bad_kep_yaml_is_skipped_not_fatal() -> None:
    """Regression: one malformed kep.yaml used to fail the whole issues stream."""
    fake = FakeGitHub()
    real_call = fake.__call__

    def broken_yaml(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"{ENH}/contents/{KEP_PATH}":
            return httpx.Response(200, text="key: [unclosed")
        return real_call(request)

    http = HttpClient(
        "https://api.github.com",
        transport=httpx.MockTransport(broken_yaml),
        policy=RetryPolicy(max_attempts=2),
        sleep=lambda s: None,
        instrument=False,
    )
    transport = InMemoryTransport()
    poller = GitHubPoller(
        gh=GitHubClient(http),
        publisher=EventPublisher(transport),
        cursors=InMemoryCursorStore(),
        calendar=load_calendar(),
        release_name="v1.38",
        now=lambda: NOW,
    )
    stats = poller.run(backfill=True)
    assert stats.failed_streams == []
    assert stats.spec_parse_errors == 1
    types = {e.event_type for e in published(transport)}
    assert "work_item.spec_observed" not in types
    assert "work_item.observed" in types


@pytest.mark.parametrize("missing", [143442])
def test_tracked_pr_not_found_is_skipped(missing: int) -> None:
    fake = FakeGitHub()
    del fake.prs[missing]
    poller, _, _ = make_poller(fake)
    stats = poller.run(backfill=True)
    assert stats.failed_streams == []
    assert stats.tracked_prs_fetched_by_number == 3


def test_code_only_mode_syncs_prs_in_the_jira_window_and_nothing_else() -> None:
    """Kafka (ADR-0018): Jira owns the plan and the release; GitHub gives PRs only."""
    fake = FakeGitHub()
    poller, transport, _ = make_poller(fake)
    poller.calendar = None
    poller.enhancements_repo = None
    poller.window = (datetime(2026, 10, 26, tzinfo=UTC), None)  # 4.5.0: no release date yet
    stats = poller.run(backfill=True)
    types = {e.event_type for e in published(transport)}
    assert stats.failed_streams == []
    assert "release.observed" not in types
    assert "work_item.observed" not in types
    assert "pull_request.observed" in types
    assert not any(r.url.path.startswith(ENH) for r in fake.requests)
    queries = {q["variables"]["q"] for q in fake.graphql_queries if "q" in q["variables"]}
    # Open-ended window runs to now.
    assert (
        "repo:kubernetes/kubernetes is:pr created:2026-10-26T00:00:00Z..2026-11-21T12:00:00Z"
        in queries
    )


def test_planning_repo_without_kep_specs_never_asks_for_them() -> None:
    """Issue #11: this project's issues made the poller ask for kep.yaml on 'master' (404)."""
    fake = FakeGitHub()
    poller, transport, _ = make_poller(fake, read_kep_specs=False)
    stats = poller.run(backfill=True)
    assert stats.failed_streams == []
    assert stats.issues_in_release == 1
    assert not any("/git/trees/" in r.url.path for r in fake.requests)
    assert not any(e.event_type == "work_item.spec_observed" for e in published(transport))
