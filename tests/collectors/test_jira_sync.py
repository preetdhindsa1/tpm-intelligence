"""Jira client and collector against a mocked Jira (no network), on the real fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

from collectors.jira.client import JiraClient
from collectors.jira.sync import JiraCollector
from pipeline.events import NormalizedEvent
from pipeline.queue import EventPublisher
from pipeline.store.cursors import InMemoryCursorStore

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "jira"
NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)


def load(name: str) -> Any:
    return json.loads((FIX / name).read_text())


def truncated(issue: dict[str, Any]) -> dict[str, Any]:
    """What search returns when Jira caps the changelog: fewer histories than ``total``."""
    log = issue["changelog"]
    return {**issue, "changelog": {"total": log["total"], "histories": log["histories"][:2]}}


class FakeJira:
    """Serves /search in pages of one, /issue/{key} and /issue/{key}/remotelink."""

    def __init__(self, issues: list[dict[str, Any]], *, truncate: bool = False) -> None:
        self.issues = {i["key"]: i for i in issues}
        self.order = [i["key"] for i in issues]
        self.truncate = truncate
        self.calls: list[str] = []
        self.jql: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/jira/rest/api/2")
        self.calls.append(path)
        if path == "/search":
            self.jql.append(request.url.params["jql"])
            start = int(request.url.params["startAt"])
            page = [self.issues[k] for k in self.order[start : start + 1]]
            if self.truncate:
                page = [truncated(i) for i in page]
            return httpx.Response(200, json={"total": len(self.order), "issues": page})
        if path.endswith("/remotelink"):
            key = path.split("/")[2]
            return httpx.Response(200, json=load(f"remotelinks_{key}.json"))
        if path.startswith("/issue/"):
            return httpx.Response(200, json=self.issues[path.split("/")[2]])
        return httpx.Response(404, json={})


def client(fake: FakeJira, sleeps: list[float] | None = None) -> JiraClient:
    clock = iter(float(i) / 10 for i in range(10_000))
    return JiraClient.from_base_url(
        "https://issues.apache.org/jira",
        transport=httpx.MockTransport(fake),
        instrument=False,
        min_interval_s=1.0,
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
        clock=lambda: next(clock),
    )


class Captured:
    """Stands in for EventPublisher."""

    def __init__(self) -> None:
        self.events: list[NormalizedEvent] = []

    def publish(self, event: NormalizedEvent) -> str:
        self.events.append(event)
        return event.event_id


def collector(jira: JiraClient, cursors: InMemoryCursorStore, out: Captured) -> JiraCollector:
    return JiraCollector(
        jira=jira,
        publisher=cast(EventPublisher, out),
        cursors=cursors,
        project="KAFKA",
        project_key="KAFKA",
        base_url="https://issues.apache.org/jira",
        releases=["4.2.0"],
        now=lambda: NOW,
    )


def test_search_pages_and_refetches_truncated_changelogs() -> None:
    issues = [load("issue_KAFKA-19831.json"), load("issue_KAFKA-21181.json")]
    fake = FakeJira(issues, truncate=True)
    sleeps: list[float] = []
    jira = client(fake, sleeps)
    got = list(jira.search("project = KAFKA"))
    assert [i["key"] for i in got] == ["KAFKA-19831", "KAFKA-21181"]
    # Each issue's full changelog was fetched because search capped it.
    assert all(len(i["changelog"]["histories"]) == i["changelog"]["total"] for i in got)
    assert jira.full_changelogs == 2
    assert fake.calls.count("/search") == 2
    assert sleeps  # requests were spaced out (polite to Apache Jira)


def test_collector_publishes_history_and_references_and_advances_the_cursor() -> None:
    fake = FakeJira([load("issue_KAFKA-19831.json")])
    cursors = InMemoryCursorStore()
    out = Captured()
    stats = collector(client(fake), cursors, out).run()
    assert not stats.failed
    assert stats.issues == 1
    types = {e.payload.type for e in out.events}
    assert {"work_item.observed", "work_item.release_changed", "reference.observed"} <= types
    # Issues that once had the version are searched too (removed items, CLAUDE.md s.6).
    assert 'fixVersion was in ("4.2.0")' in fake.jql[0]
    from collectors.jira.normalize import parse_ts

    stream = collector(client(fake), cursors, out).stream
    updated = parse_ts(load("issue_KAFKA-19831.json")["fields"]["updated"])
    assert cursors.get(stream) == updated.isoformat()


def test_incremental_run_overlaps_by_a_day() -> None:
    fake = FakeJira([load("issue_KAFKA-19831.json")])
    cursors = InMemoryCursorStore()
    c = collector(client(fake), cursors, Captured())
    cursors.record_success(c.stream, "2026-11-20T10:30:00+00:00", NOW)
    c.run()
    assert 'updated >= "2026/11/19 10:30"' in fake.jql[0]
    assert fake.jql[0].endswith("ORDER BY updated ASC")


def test_failure_keeps_the_cursor_and_counts_it() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errorMessages": ["bad jql"]})

    jira = JiraClient.from_base_url(
        "https://issues.apache.org/jira", transport=httpx.MockTransport(broken), instrument=False
    )
    cursors = InMemoryCursorStore()
    c = collector(jira, cursors, Captured())
    cursors.record_success(c.stream, "2026-11-20T10:30:00+00:00", NOW)
    stats = c.run()
    assert stats.failed
    assert cursors.get(c.stream) == "2026-11-20T10:30:00+00:00"
    assert cursors.failures[c.stream] == 1


def test_backfill_has_no_date_filter() -> None:
    c = collector(client(FakeJira([])), InMemoryCursorStore(), Captured())
    assert "updated >=" not in c.jql(None)
