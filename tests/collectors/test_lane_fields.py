"""Lane fields on a PR snapshot: paths and messages, never patches."""

from __future__ import annotations

from datetime import UTC, datetime

from collectors.github_poller import normalize as poll
from collectors.github_webhooks import normalize as hook

OBS = datetime(2026, 12, 1, tzinfo=UTC)


def test_lane_node_stores_paths_messages_and_a_conflict() -> None:
    node = {
        "number": 7,
        "title": "lab",
        "body": "",
        "url": "https://github.com/preetdhindsa1/tpm-intelligence/pull/7",
        "state": "OPEN",
        "createdAt": "2026-12-01T00:00:00Z",
        "updatedAt": "2026-12-01T01:00:00Z",
        "mergedAt": None,
        "closedAt": None,
        "baseRefName": "main",
        "headRefName": "cursor/7-lab",
        "additions": 10,
        "deletions": 2,
        "mergeable": "CONFLICTING",
        "repository": {"nameWithOwner": "preetdhindsa1/tpm-intelligence"},
        "author": {"login": "octocat"},
        "labels": {"nodes": [{"name": "cursor-agent"}]},
        "files": {
            "pageInfo": {"hasNextPage": False},
            "nodes": [{"path": "engine/lab.py"}, {"path": "README.md"}],
        },
        "history": {
            "pageInfo": {"hasNextPage": False},
            "nodes": [
                {
                    "commit": {
                        "committedDate": "2026-12-01T00:30:00Z",
                        "messageHeadline": "lab",
                        "messageBody": "Co-authored-by: Cursor Agent",
                    }
                }
            ],
        },
        "reviews": {"nodes": []},
        "comments": {"nodes": []},
        "commits": {
            "nodes": [
                {
                    "commit": {
                        "oid": "abc",
                        "statusCheckRollup": None,
                    }
                }
            ]
        },
    }
    events = poll.pull_request_events(node, observed_at=OBS)
    snap = events[0].payload
    assert snap.head_ref == "cursor/7-lab"  # type: ignore[attr-defined]
    assert snap.changed_files == ("engine/lab.py", "README.md")  # type: ignore[attr-defined]
    assert snap.additions == 10  # type: ignore[attr-defined]
    assert "Cursor Agent" in snap.commits[0].message  # type: ignore[attr-defined]
    assert events[1].event_type == "pull_request.mergeability_observed"
    assert events[1].payload.mergeable == "conflicting"  # type: ignore[attr-defined]


def test_node_without_lane_fields_stays_at_defaults() -> None:
    node = {
        "number": 8,
        "title": "plain",
        "body": "",
        "url": None,
        "state": "OPEN",
        "createdAt": "2026-12-01T00:00:00Z",
        "updatedAt": "2026-12-01T01:00:00Z",
        "mergedAt": None,
        "closedAt": None,
        "baseRefName": "main",
        "repository": {"nameWithOwner": "kubernetes/kubernetes"},
        "author": {"login": "octocat"},
        "labels": {"nodes": []},
        "reviews": {"nodes": []},
        "comments": {"nodes": []},
        "commits": {"nodes": []},
    }
    [event] = poll.pull_request_events(node, observed_at=OBS)
    assert event.payload.head_ref is None  # type: ignore[attr-defined]
    assert event.payload.changed_files == ()  # type: ignore[attr-defined]
    assert event.event_type == "pull_request.observed"


def test_webhook_records_the_branch_and_skips_a_null_mergeable() -> None:
    pr = {
        "number": 9,
        "title": "hook",
        "body": "",
        "html_url": "https://github.com/preetdhindsa1/tpm-intelligence/pull/9",
        "state": "open",
        "merged": False,
        "created_at": "2026-12-01T00:00:00Z",
        "updated_at": "2026-12-01T01:00:00Z",
        "merged_at": None,
        "closed_at": None,
        "user": {"login": "octocat"},
        "labels": [],
        "base": {"ref": "main"},
        "head": {"ref": "harpreet/9-docs", "sha": "def"},
        "mergeable": None,
        "mergeable_state": "unknown",
    }
    snap = hook.pull_request_snapshot("preetdhindsa1/tpm-intelligence", pr, observed_at=OBS)
    assert snap.payload.head_ref == "harpreet/9-docs"  # type: ignore[attr-defined]
    assert snap.payload.changed_files == ()  # type: ignore[attr-defined]
    assert hook.mergeability_event("preetdhindsa1/tpm-intelligence", pr, observed_at=OBS) is None
