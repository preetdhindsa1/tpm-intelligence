"""Who merged a PR is stored (ADR-0023 addendum 3), and storing it re-saves old merged PRs
once, so fields added after they merged (commits, for lanes) reach the store."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from collectors.github_poller import normalize as poll
from collectors.github_webhooks import normalize as hook
from pipeline.events import PullRequestObserved

OBS = datetime(2026, 11, 25, tzinfo=UTC)


def _node(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": 67, "title": "Security review", "body": "", "url": "u", "state": "MERGED",
        "createdAt": "2026-11-24T01:00:00Z", "updatedAt": "2026-11-24T03:00:00Z",
        "mergedAt": "2026-11-24T03:00:00Z", "closedAt": "2026-11-24T03:00:00Z",
        "baseRefName": "main", "repository": {"nameWithOwner": "preetdhindsa1/tpm-intelligence"},
        "author": {"login": "preetdhindsa1"}, "labels": {"nodes": []},
        "reviews": {"pageInfo": {"hasNextPage": False}, "nodes": []},
        "comments": {"pageInfo": {"hasNextPage": False}, "nodes": []},
        "commits": {"nodes": []},
    }  # fmt: skip
    return {**base, **kw}


def _snapshot(events: list[Any]) -> Any:
    return next(e for e in events if isinstance(e.payload, PullRequestObserved))


def test_poller_stores_who_merged_and_gives_the_snapshot_a_new_id() -> None:
    merged = _snapshot(
        poll.pull_request_events(_node(mergedBy={"login": "preetdhindsa1"}), observed_at=OBS)
    )
    before = _snapshot(poll.pull_request_events(_node(), observed_at=OBS))
    assert merged.payload.merged_by == "preetdhindsa1"
    assert before.payload.merged_by is None
    assert merged.event_id != before.event_id  # re-stored once on the next sync
    again = _snapshot(
        poll.pull_request_events(_node(mergedBy={"login": "preetdhindsa1"}), observed_at=OBS)
    )
    assert again.event_id == merged.event_id  # then stable


def test_open_prs_keep_their_snapshot_ids() -> None:
    open_node = _node(state="OPEN", mergedAt=None, closedAt=None, mergedBy=None)
    a = _snapshot(poll.pull_request_events(open_node, observed_at=OBS))
    b = _snapshot(poll.pull_request_events({**open_node}, observed_at=OBS))
    assert a.payload.merged_by is None
    assert a.event_id == b.event_id


def test_webhook_reads_merged_by_from_the_rest_payload() -> None:
    pr = {"number": 67, "title": "t", "user": {"login": "preetdhindsa1"}, "state": "closed",
          "merged": True, "merged_at": "2026-11-24T03:00:00Z", "closed_at": "2026-11-24T03:00:00Z",
          "created_at": "2026-11-24T01:00:00Z", "updated_at": "2026-11-24T03:00:00Z",
          "merged_by": {"login": "preetdhindsa1"}, "labels": []}  # fmt: skip
    e = hook.pull_request_snapshot("preetdhindsa1/tpm-intelligence", pr, observed_at=OBS)
    assert isinstance(e.payload, PullRequestObserved)
    assert e.payload.merged_by == "preetdhindsa1"
