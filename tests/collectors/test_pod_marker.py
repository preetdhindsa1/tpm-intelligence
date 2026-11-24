"""Pod marker (ADR-0023 addendum): who wrote a review when every agent posts as the owner."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from collectors.github_poller.normalize import (
    comment_events,
    pod_marker,
    pull_request_ref,
    review_events,
)
from collectors.github_webhooks.normalize import review_event
from engine.projection import project
from engine.review_rounds import review_rounds
from pipeline.events import PullRequestObserved, Source, new_event

FIXTURE = Path(__file__).parents[1] / "fixtures" / "github" / "review_cross_review_106.json"
REPO = "preetdhindsa1/tpm-intelligence"
OBSERVED = datetime(2026, 11, 25, tzinfo=UTC)
AT, MARK = "2026-11-24T23:45:18Z", "Cross-review · claude-agent"


def test_marker_rule() -> None:
    assert pod_marker("Cross-review · claude-agent\n\nRead the diff") == "cross-review:claude-agent"
    assert pod_marker("\n  **Reply · cursor-agent**\nFixed") == "reply:cursor-agent"
    assert pod_marker("great work but we need further improvement") is None
    assert pod_marker("LGTM - thanks") is None  # a plain hyphen is not the marker
    assert pod_marker("/lgtm\nCross-review · claude-agent") is None  # first line only
    assert pod_marker(None) is None


def test_real_cross_review_on_106_keeps_only_the_tag() -> None:
    review = json.loads(FIXTURE.read_text())
    event = review_event(REPO, 106, review, observed_at=OBSERVED)
    assert event is not None
    assert event.payload.marker == "cross-review:claude-agent"  # type: ignore[union-attr]
    assert "Read the full diff" not in event.model_dump_json()  # text is never stored


def test_poller_and_webhook_agree_and_unmarked_ids_do_not_change() -> None:
    subject = pull_request_ref(REPO, 106)
    node = {"databaseId": 1, "author": {"login": "o"}, "state": "COMMENTED",
            "submittedAt": AT, "body": MARK}  # fmt: skip
    (marked,) = review_events([node], subject=subject, observed_at=OBSERVED)
    (plain,) = review_events([{**node, "body": "ok"}], subject=subject, observed_at=OBSERVED)
    (old,) = review_events([{**node, "body": None}], subject=subject, observed_at=OBSERVED)
    assert marked.payload.marker == "cross-review:claude-agent"  # type: ignore[union-attr]
    assert plain.event_id == old.event_id  # ids of records without a marker are unchanged
    assert marked.event_id != old.event_id  # stored again once its marker is read
    rest = {"id": 1, "user": {"login": "o"}, "state": "COMMENTED",
            "submitted_at": AT, "body": MARK}  # fmt: skip
    hook = review_event(REPO, 106, rest, observed_at=OBSERVED)
    assert hook is not None
    assert hook.payload.marker == marked.payload.marker  # type: ignore[union-attr]


def test_projection_keeps_the_marker_whatever_the_order_and_rounds_are_unchanged() -> None:
    subject = pull_request_ref(REPO, 106)
    opened = datetime(2026, 11, 24, 22, tzinfo=UTC)
    pr = new_event(
        source=Source.GITHUB, subject=subject, occurred_at=opened, observed_at=OBSERVED,
        identity=(106,), payload=PullRequestObserved(
            repo=REPO, number=106, title="UX v1 A", state="open", author="owner",
            created_at=opened, updated_at=opened),
    )  # fmt: skip
    node = {"databaseId": 7, "author": {"login": "reviewer"}, "createdAt": "2026-11-24T23:45:18Z"}
    (old,) = comment_events([{**node, "body": "x"}], subject=subject, observed_at=OBSERVED)
    (new,) = comment_events([{**node, "body": "Cross-review · claude-agent"}], subject=subject,
                            observed_at=OBSERVED)  # fmt: skip
    for events in ([pr, old, new], [pr, new, old]):
        world = project(events, OBSERVED)
        (comment,) = world.pull_requests[f"{REPO}#106"].comments
        assert comment.marker == "cross-review:claude-agent"
        (rnd,) = review_rounds(world.pull_requests[f"{REPO}#106"])
        assert rnd.reviewer == "reviewer"  # the marker does not change review rounds
