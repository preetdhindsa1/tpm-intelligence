"""GraphQL drops "[bot]" from app logins (ADR-0012 addendum, #97). Real shapes from
kubernetes/kubernetes#144449 on 2026-11-25: REST `kubernetes-prow[bot]` (type Bot),
GraphQL `{"login": "kubernetes-prow", "__typename": "Bot"}`."""

from __future__ import annotations

from datetime import UTC, datetime

from collectors.github_poller.normalize import actor_login, comment_events, pull_request_ref
from engine.review_rounds import is_bot

OBSERVED = datetime(2026, 11, 25, tzinfo=UTC)
SUBJECT = pull_request_ref("kubernetes/kubernetes", 144449)


def node(login: str, typename: str) -> dict[str, object]:
    return {
        "databaseId": 1,
        "createdAt": "2026-11-24T18:00:05Z",
        "body": "Hi",
        "author": {"login": login, "__typename": typename},
    }


def test_app_logins_get_the_rest_spelling_and_people_do_not_change() -> None:
    assert actor_login({"login": "kubernetes-prow", "__typename": "Bot"}) == "kubernetes-prow[bot]"
    assert actor_login({"login": "dependabot[bot]", "__typename": "Bot"}) == "dependabot[bot]"
    assert actor_login({"login": "a-reviewer", "__typename": "User"}) == "a-reviewer"
    assert actor_login({"login": "old-shape"}) == "old-shape"  # stored before __typename
    assert actor_login(None) is None
    for app in ("kubernetes-prow", "linux-foundation-easycla", "copilot-pull-request-reviewer"):
        assert is_bot(actor_login({"login": app, "__typename": "Bot"}) or "")


def test_bot_comments_are_stored_again_and_people_keep_their_event_ids() -> None:
    (bot,) = comment_events([node("kubernetes-prow", "Bot")], subject=SUBJECT, observed_at=OBSERVED)
    (old,) = comment_events(
        [{**node("kubernetes-prow", "Bot"), "author": {"login": "kubernetes-prow"}}],
        subject=SUBJECT,
        observed_at=OBSERVED,
    )
    assert bot.payload.author == "kubernetes-prow[bot]"  # type: ignore[union-attr]
    assert bot.event_id != old.event_id  # a backfill re-stores it with the right login
    (person,) = comment_events([node("a-reviewer", "User")], subject=SUBJECT, observed_at=OBSERVED)
    (before,) = comment_events(
        [{**node("a-reviewer", "User"), "author": {"login": "a-reviewer"}}],
        subject=SUBJECT,
        observed_at=OBSERVED,
    )
    assert person.event_id == before.event_id
