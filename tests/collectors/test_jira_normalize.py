"""Jira issues -> normalized events, on the real KAFKA-19831 / KAFKA-21181 fixtures.

KAFKA-19831: links to KAFKA-17789; Fix Version changed 3 times (CLAUDE.md section 11).
KAFKA-21181: In Progress while tagged with released versions 4.0.0-4.3.0; 4.2.0 and 4.3.0
were set at creation, so they are missing from the changelog.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collectors.jira import normalize as n
from pipeline.events import ChangeAction, WorkItemType

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "jira"
OBSERVED = datetime(2026, 11, 22, 12, tzinfo=UTC)
BASE = "https://issues.apache.org/jira"


def load(name: str) -> Any:
    return json.loads((FIX / name).read_text())


def releases(events: list[Any]) -> list[tuple[str, str, str]]:
    return [
        (e.occurred_at.date().isoformat(), e.payload.action.value, e.payload.release_key)
        for e in events
        if e.payload.type == "work_item.release_changed"
    ]


def test_snapshot_of_21181_keeps_all_four_released_fix_versions() -> None:
    issue = load("issue_KAFKA-21181.json")
    e = n.issue_snapshot(issue, project="KAFKA", base_url=BASE, observed_at=OBSERVED)
    p = e.payload
    assert e.subject.external_key == "KAFKA-21181"
    assert e.subject.source.value == "jira"
    assert p.state == "In Progress"
    assert p.status_category == "in_progress"
    assert p.item_type is WorkItemType.BUG
    assert p.release_keys == ("KAFKA:4.0.0", "KAFKA:4.1.0", "KAFKA:4.2.0", "KAFKA:4.3.0")
    assert p.url == "https://issues.apache.org/jira/browse/KAFKA-21181"


def test_versions_set_at_creation_are_rebuilt_from_the_changelog() -> None:
    issue = load("issue_KAFKA-21181.json")
    assert n.initial_fix_versions(issue) == {"4.2.0", "4.3.0"}
    events = n.issue_history(issue, project="KAFKA", observed_at=OBSERVED)
    added = {k for _, action, k in releases(events) if action == "added"}
    assert added == {"KAFKA:4.0.0", "KAFKA:4.1.0", "KAFKA:4.2.0", "KAFKA:4.3.0"}
    created = issue["fields"]["created"][:10]
    assert "KAFKA:4.3.0" in {k for d, _, k in releases(events) if d == created}


def test_19831_fix_version_changed_three_times() -> None:
    issue = load("issue_KAFKA-19831.json")
    events = n.issue_history(issue, project="KAFKA", observed_at=OBSERVED)
    changes = [r for r in releases(events) if r[0] != issue["fields"]["created"][:10]]
    assert changes == [
        ("2025-11-21", "added", "KAFKA:4.2.0"),
        ("2025-12-02", "added", "KAFKA:4.1.2"),
        ("2026-02-10", "added", "KAFKA:4.0.2"),
    ]
    statuses = [
        (e.payload.to_state, e.payload.to_category)
        for e in events
        if e.payload.type == "work_item.status_changed"
    ]
    assert ("In Progress", "in_progress") in statuses
    assert ("Resolved", "done") in statuses


def test_folding_history_gives_the_current_fix_versions() -> None:
    for name in ("issue_KAFKA-19831.json", "issue_KAFKA-21181.json"):
        issue = load(name)
        state: set[str] = set()
        for _, action, key in releases(
            n.issue_history(issue, project="KAFKA", observed_at=OBSERVED)
        ):
            (state.add if action == ChangeAction.ADDED.value else state.discard)(key)
        assert state == {f"KAFKA:{v['name']}" for v in issue["fields"]["fixVersions"]}


def test_remote_links_to_github_prs_become_references() -> None:
    events = n.remote_link_events(
        "KAFKA-19831", load("remotelinks_KAFKA-19831.json"), observed_at=OBSERVED
    )
    keys = [e.payload.pull_request.external_key for e in events]
    assert "apache/kafka#20767" in keys
    assert all(e.payload.evidence == "remote_link" for e in events)
    assert n.pull_request_ref("https://cwiki.apache.org/confluence/display/KAFKA/KIP-1") is None


def test_event_ids_are_stable_across_runs() -> None:
    issue = load("issue_KAFKA-19831.json")
    a = [e.event_id for e in n.issue_history(issue, project="KAFKA", observed_at=OBSERVED)]
    b = [e.event_id for e in n.issue_history(issue, project="KAFKA", observed_at=datetime.now(UTC))]
    assert a == b
    assert len(set(a)) == len(a)


def test_status_categories_prefer_team_overrides_then_jira() -> None:
    assert n.category("Patch Available") == "in_progress"
    assert n.category("Resolved", "done") == "done"
    assert n.category("Resolved", "done", {"Resolved": "in_progress"}) == "in_progress"
    assert n.category("Brand New Status", "new") == "todo"


def test_no_person_fields_in_fixtures() -> None:
    for path in FIX.glob("*.json"):
        text = path.read_text()
        assert "displayName" not in text
        assert "emailAddress" not in text
