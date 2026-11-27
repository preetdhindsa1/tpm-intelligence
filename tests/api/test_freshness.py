"""Release freshness from collector sync health (ADR-0036)."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from api.freshness import release_freshness
from api.main import create_app
from api.service import InMemoryEventSource, ReleaseService
from api.validation import Validation
from connectors.load import load_teams
from pipeline.store.cursors import StreamHealth
from tests.api.test_api import FAST
from tests.engine.conftest import fixture_events, utc

NOW = utc(2026, 11, 21, 3)
RELEASE_AT = utc(2026, 12, 16)
K8S_ISSUES = "github:kubernetes/enhancements:issues:v1.38"
K8S_PRS = "github:kubernetes/kubernetes:prs:v1.38"


def _ok(stream: str, minutes: float, failures: int = 0) -> StreamHealth:
    return StreamHealth(stream, NOW - timedelta(minutes=minutes), failures)


def test_fresh_when_every_source_is_within_its_threshold() -> None:
    k8s = load_teams()["kubernetes"]
    f = release_freshness(k8s, "v1.38", RELEASE_AT, [_ok(K8S_ISSUES, 4), _ok(K8S_PRS, 9)], NOW)
    assert f.status == "fresh"
    assert f.as_of == NOW - timedelta(minutes=9)  # the stalest source
    assert [(s.kind, s.system, s.age_minutes) for s in f.sources] == [
        ("planning", "github", 4.0),
        ("code", "github", 9.0),
    ]


def test_one_failing_source_makes_the_release_stale() -> None:
    k8s = load_teams()["kubernetes"]
    streams = [_ok(K8S_ISSUES, 4), _ok(K8S_PRS, 25, failures=4)]
    f = release_freshness(k8s, "v1.38", RELEASE_AT, streams, NOW)
    assert f.status == "stale"
    assert [s.stale for s in f.sources] == [False, True]
    assert f.sources[1].consecutive_failures == 4


def test_a_stream_that_never_succeeded_is_stale_with_no_as_of() -> None:
    k8s = load_teams()["kubernetes"]
    streams = [_ok(K8S_ISSUES, 1), StreamHealth(K8S_PRS, None, 2)]
    f = release_freshness(k8s, "v1.38", RELEASE_AT, streams, NOW)
    assert (f.status, f.as_of) == ("stale", None)


def test_jira_has_its_hourly_threshold_and_joined_release_streams() -> None:
    kafka = load_teams()["kafka"]
    streams = [
        _ok("jira:KAFKA:issues:4.4.0+4.5.0", 65),  # hourly sync: still fresh
        _ok("github:apache/kafka:prs:4.5.0", 3),
        _ok("github:apache/kafka:prs:4.4.0", 500),  # another release
        _ok(K8S_PRS, 500),  # another team
    ]
    f = release_freshness(kafka, "4.5.0", RELEASE_AT, streams, NOW)
    assert f.status == "fresh"
    assert [(s.kind, s.system) for s in f.sources] == [("planning", "jira"), ("code", "github")]
    late = release_freshness(kafka, "4.5.0", RELEASE_AT, [_ok("jira:KAFKA:issues:4.5.0", 71)], NOW)
    assert late.status == "stale"


def test_a_shipped_release_is_final_not_stale() -> None:
    k8s = load_teams()["kubernetes"]
    after = RELEASE_AT + timedelta(days=4)
    streams = [StreamHealth(K8S_PRS, RELEASE_AT, 0)]
    assert release_freshness(k8s, "v1.38", RELEASE_AT, streams, after).status == "final"


def test_no_sync_records_is_unknown_never_fresh() -> None:
    k8s = load_teams()["kubernetes"]
    f = release_freshness(k8s, "v1.38", RELEASE_AT, [], NOW)
    assert (f.status, f.as_of, f.sources) == ("unknown", None, ())


def _client(streams: list[StreamHealth]) -> TestClient:
    service = ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=FAST,
        now=lambda: NOW,
        validation=lambda: Validation(False, "test: not validated"),
    )
    return TestClient(create_app(service=service, stream_health=lambda: streams))


def test_route_reports_sources_without_error_text() -> None:
    body = _client([_ok(K8S_ISSUES, 2), _ok(K8S_PRS, 30, failures=3)]).get(
        "/releases/v1.38/freshness"
    )
    assert body.status_code == 200
    out = body.json()
    assert out["release"] == "kubernetes:v1.38"
    assert out["status"] == "stale"
    assert out["sources"][1] == {
        "kind": "code",
        "system": "github",
        "last_success_at": "2026-11-21T02:30:00Z",
        "age_minutes": 30.0,
        "consecutive_failures": 3,
        "stale": True,
        "stale_after_minutes": 10,
    }
    assert "error" not in body.text


def test_route_404_for_an_unknown_release() -> None:
    assert _client([]).get("/releases/v9.99/freshness").status_code == 404
