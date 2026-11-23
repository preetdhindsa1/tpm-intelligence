"""Webhook payloads give the same event IDs as the poller for the same facts (ADR-0020).

The poller keeps running as a reconciliation pass, so a review, comment, check or PR
snapshot that arrives by webhook and by poll must be stored once. Fixtures: GraphQL
(poller) and REST (webhook shape) data for kubernetes/kubernetes#143709.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from collectors.github_poller import normalize as poll
from collectors.github_webhooks import normalize as hook
from connectors.load import load_team
from tests.collectors.conftest import load_json

OBS = datetime(2026, 11, 23, 12, tzinfo=UTC)
KK = "kubernetes/kubernetes"


def node_143709() -> dict[str, Any]:
    return next(n for n in load_json("prs_6395.json") if n["number"] == 143709)


def test_pr_snapshot_has_the_pollers_id_and_facts() -> None:
    node = node_143709()
    polled = poll.pull_request_events(node, observed_at=OBS)[0]
    pr = load_json("webhook_pull_request_143709.json")["pull_request"]
    hooked = hook.pull_request_snapshot(KK, pr, observed_at=OBS)
    assert hooked.event_id == polled.event_id
    for field in ("state", "created_at", "merged_at", "closed_at", "updated_at", "base_ref"):
        assert getattr(hooked.payload, field) == getattr(polled.payload, field), field


def test_all_97_reviews_have_the_pollers_ids() -> None:
    node = node_143709()
    subject = poll.pull_request_ref(KK, 143709)
    polled = {
        e.event_id: e.payload
        for e in poll.review_events(node["reviews"]["nodes"], subject=subject, observed_at=OBS)
    }
    hooked = [
        hook.review_event(KK, 143709, r, observed_at=OBS)
        for r in load_json("webhook_reviews_143709.json")
    ]
    hooked_ids = {e.event_id: e.payload for e in hooked if e is not None}
    assert len(hooked_ids) == 97
    assert set(hooked_ids) == set(polled)
    for event_id, payload in hooked_ids.items():
        assert payload.state == polled[event_id].state  # type: ignore[attr-defined]
        assert payload.submitted_at == polled[event_id].submitted_at  # type: ignore[attr-defined]


def test_comment_ids_and_commands_match_the_poller() -> None:
    subject = poll.pull_request_ref(KK, 143709)
    rest = load_json("webhook_comments_143709.json")
    as_graphql = [
        {
            "databaseId": c["id"],
            "createdAt": c["created_at"],
            "author": c["user"],
            "body": c["body"],
        }
        for c in rest
    ]
    polled = poll.comment_events(as_graphql, subject=subject, observed_at=OBS)
    hooked = [hook.comment_event(KK, 143709, c, observed_at=OBS) for c in rest]
    assert [e.event_id for e in hooked] == [e.event_id for e in polled]
    assert hooked[-1].payload.commands == ("hold",)  # type: ignore[attr-defined]


def test_check_run_matches_the_pollers_check_context() -> None:
    run = {
        "name": "unit-tests",
        "head_sha": "826dcfc0",
        "status": "completed",
        "conclusion": "failure",
        "completed_at": "2026-11-20T10:00:00Z",
        "pull_requests": [{"number": 143709}],
    }
    [hooked] = hook.check_events(KK, run, observed_at=OBS)
    commit = {
        "oid": "826dcfc0",
        "statusCheckRollup": {
            "contexts": {
                "nodes": [
                    {
                        "__typename": "CheckRun",
                        "name": "unit-tests",
                        "conclusion": "FAILURE",
                        "completedAt": "2026-11-20T10:00:00Z",
                    }
                ]
            }
        },
    }
    subject = poll.pull_request_ref(KK, 143709)
    [polled] = poll._check_events(commit, "826dcfc0", subject, OBS, OBS)
    assert hooked.event_id == polled.event_id
    # A run still in progress is pending with no time, as in the poller.
    [pending] = hook.check_events(
        KK,
        {**run, "status": "in_progress", "conclusion": None, "completed_at": None},
        observed_at=OBS,
    )
    assert pending.payload.conclusion.value == "pending"  # type: ignore[attr-defined]


def test_routing_by_repository_and_event() -> None:
    n = hook.WebhookNormalizer([load_team("kubernetes")])
    pr = load_json("webhook_pull_request_143709.json")["pull_request"]
    review = load_json("webhook_reviews_143709.json")[0]
    repo = {"full_name": KK}
    got = n(
        "pull_request_review",
        {"action": "submitted", "repository": repo, "pull_request": pr, "review": review},
        OBS,
    )
    assert [e.event_type for e in got] == ["pull_request.observed", "pull_request.review_submitted"]
    # A comment on a plain issue (not a PR) in a code repo is not stored by the poller either.
    plain = {
        "action": "created",
        "repository": repo,
        "issue": {"number": 1},
        "comment": {"id": 1, "created_at": "2026-11-20T10:00:00Z"},
    }
    assert n("issue_comment", plain, OBS) == []
    assert (
        n("pull_request", {"repository": {"full_name": "someone/else"}, "pull_request": pr}, OBS)
        == []
    )
    assert "kubernetes/kubernetes" in n.repos
    assert "kubernetes/enhancements" in n.repos


def test_planning_issue_uses_the_timeline_for_history_ids() -> None:
    issue = load_json("issue_6395.json")
    timeline = poll.timeline_to_events(load_json("issue_6395_timeline.json"))
    n = hook.WebhookNormalizer([load_team("kubernetes")], timeline=lambda repo, number: timeline)
    got = n(
        "issues",
        {
            "action": "milestoned",
            "repository": {"full_name": "kubernetes/enhancements"},
            "issue": issue,
        },
        OBS,
    )
    polled = [
        poll.issue_snapshot(
            issue, repo="kubernetes/enhancements", project="kubernetes", observed_at=OBS
        ),
        *poll.issue_history(
            timeline,
            repo="kubernetes/enhancements",
            number=6395,
            project="kubernetes",
            observed_at=OBS,
        ),
    ]
    assert [e.event_id for e in got] == [e.event_id for e in polled]
    removals = [
        e
        for e in got
        if e.event_type == "work_item.release_changed" and e.payload.action == "removed"
    ]  # type: ignore[attr-defined]
    assert removals  # #6395 was removed at Code Freeze


def test_planning_and_code_in_the_same_repository() -> None:
    """The demo team plans in issues and codes in PRs of one repository."""
    n = hook.WebhookNormalizer([load_team("demo")], timeline=lambda repo, number: [])
    repo = {"full_name": "preetdhindsa1/program-demo-team"}
    issue = {**load_json("issue_6395.json"), "number": 3}
    got = n("issues", {"action": "opened", "repository": repo, "issue": issue}, OBS)
    assert [e.subject.external_key for e in got] == ["preetdhindsa1/program-demo-team#3"]
    assert got[0].event_type == "work_item.observed"
    pr = {**load_json("webhook_pull_request_143709.json")["pull_request"], "number": 4}
    got = n("pull_request", {"action": "opened", "repository": repo, "pull_request": pr}, OBS)
    assert [e.event_type for e in got] == ["pull_request.observed"]
