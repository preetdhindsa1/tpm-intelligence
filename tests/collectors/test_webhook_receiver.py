"""Webhook receiver (P3-M5): only signed deliveries from allowed repos get published."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from collectors.github_webhooks.app import MAX_BODY_BYTES, RecentDeliveries, create_app
from collectors.github_webhooks.signature import sign, verify
from pipeline.events import NormalizedEvent
from tests.engine.synthetic import Stream

SECRET = "test-secret"  # noqa: S105 - test fixture, not a credential
NOW = datetime(2026, 11, 23, 12, tzinfo=UTC)
REPO = "preetdhindsa1/tpm-demo-team"


def one_event() -> NormalizedEvent:
    s = Stream(NOW)
    s.pr(7, 1, NOW)
    return s.events[0]


def client() -> tuple[TestClient, list[NormalizedEvent], list[tuple[str, dict[str, Any]]]]:
    published: list[NormalizedEvent] = []
    seen: list[tuple[str, dict[str, Any]]] = []

    def normalize(event: str, payload: dict[str, Any], at: datetime) -> list[NormalizedEvent]:
        seen.append((event, payload))
        return [one_event()] if event == "pull_request" else []

    app = create_app(
        secret=SECRET,
        publish=published.append,
        normalize=normalize,
        allowed_repos=[REPO],
        now=lambda: NOW,
    )
    return TestClient(app), published, seen


def post(
    c: TestClient,
    event: str,
    payload: dict[str, Any],
    *,
    delivery: str = "d-1",
    secret: str = SECRET,
    signature: str | None = None,
) -> Any:
    body = json.dumps(payload).encode()
    headers = {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": signature if signature is not None else sign(secret, body),
        "Content-Type": "application/json",
    }
    return c.post("/github", content=body, headers=headers)


PAYLOAD = {"action": "opened", "repository": {"full_name": REPO}}


def test_signature_check() -> None:
    body = b'{"a": 1}'
    assert verify(SECRET, body, sign(SECRET, body))
    assert not verify(SECRET, body, sign("other", body))
    assert not verify(SECRET, body, None)
    assert not verify(SECRET, body, "sha1=abc")
    assert not verify("", body, sign("", body))  # no secret configured: accept nothing


def test_signed_delivery_is_normalized_and_published() -> None:
    c, published, seen = client()
    r = post(c, "pull_request", PAYLOAD)
    assert r.status_code == 202
    assert r.json() == {"events": 1}
    assert [e for e, _ in seen] == ["pull_request"]
    assert len(published) == 1


def test_unsigned_or_wrongly_signed_is_rejected_and_not_read() -> None:
    c, published, seen = client()
    wrong = "wrong"
    assert post(c, "pull_request", PAYLOAD, secret=wrong).status_code == 401
    assert post(c, "pull_request", PAYLOAD, signature="").status_code == 401
    assert published == []
    assert seen == []


def test_ping_and_repeat_deliveries() -> None:
    c, published, _ = client()
    assert post(c, "ping", {"zen": "hi"}).text == "pong"
    assert post(c, "pull_request", PAYLOAD, delivery="d-9").status_code == 202
    assert post(c, "pull_request", PAYLOAD, delivery="d-9").status_code == 202  # retry
    assert len(published) == 1


def test_repository_no_team_lists_is_dropped() -> None:
    c, published, seen = client()
    other = {"action": "opened", "repository": {"full_name": "someone/else"}}
    assert post(c, "pull_request", other).status_code == 202
    assert published == []
    assert seen == []


def test_oversized_and_malformed_bodies() -> None:
    c, published, _ = client()
    big = b"x" * (MAX_BODY_BYTES + 1)
    r = c.post(
        "/github",
        content=big,
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": sign(SECRET, big)},
    )
    assert r.status_code == 413
    bad = b"not json"
    r = c.post(
        "/github",
        content=bad,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "d-2",
            "X-Hub-Signature-256": sign(SECRET, bad),
        },
    )
    assert r.status_code == 400
    assert published == []


def test_unhandled_event_types_are_acknowledged() -> None:
    c, published, _ = client()
    r = post(c, "star", PAYLOAD, delivery="d-3")
    assert r.status_code == 202
    assert r.json() == {"events": 0}
    assert published == []


def test_recent_deliveries_forget_the_oldest() -> None:
    recent = RecentDeliveries(size=2)
    assert not recent.seen("a")
    assert not recent.seen("b")
    assert not recent.seen("c")  # "a" is forgotten
    assert not recent.seen("a")
    assert recent.seen("c")
