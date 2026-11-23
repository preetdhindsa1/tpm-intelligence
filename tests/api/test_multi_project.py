"""Two projects in one store (ADR-0018): Kubernetes (#6395 fixtures) and Kafka (Jira).

Each project gets its own world: Kafka PRs are not Kubernetes load, bare release names
resolve to the right project, and Jira features are found by their key's number.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app
from api.service import InMemoryEventSource, ReleaseService
from api.validation import Validation
from connectors.load import load_team, scope_events
from engine.forecast import ForecastConfig
from tests.engine.conftest import fixture_events, utc
from tests.engine.test_kafka_world import events as kafka_events

FAST = ForecastConfig(replications=5, sims=100)
NOW = utc(2026, 11, 22, 13)


def service() -> ReleaseService:
    return ReleaseService(
        InMemoryEventSource([*fixture_events(), *kafka_events()]),
        forecast=FAST,
        now=lambda: NOW,
        validation=lambda: Validation(False, "test: not validated"),
    )


def test_team_owns_its_releases_plan_and_code() -> None:
    kafka, k8s = load_team("kafka"), load_team("kubernetes")
    assert kafka.owns("KAFKA:4.4.0")
    assert kafka.owns("KAFKA-20682")
    assert kafka.owns("apache/kafka#22666")
    assert not kafka.owns("kubernetes/kubernetes#143709")
    assert k8s.owns("kubernetes/enhancements#6395")
    assert not k8s.owns("apache/kafka#22666")
    assert not k8s.owns("KAFKA-20682")


def test_scoped_events_hold_one_project_only() -> None:
    both = [*fixture_events(), *kafka_events()]
    keys = {e.subject.external_key for e in scope_events(both, "kubernetes")}
    assert not any(k.startswith(("KAFKA", "apache/")) for k in keys)
    kafka = {e.subject.external_key for e in scope_events(both, "KAFKA")}
    assert "KAFKA:4.4.0" in kafka
    assert not any(k.startswith("kubernetes") for k in kafka)


def test_bare_names_resolve_per_project_and_worlds_are_separate() -> None:
    s = service()
    assert s.resolve("4.4.0") == "KAFKA:4.4.0"
    assert s.resolve("v1.38") == "kubernetes:v1.38"
    kafka = s.view("4.4.0")
    assert set(kafka.world.releases) == {"KAFKA:4.4.0"}
    assert all(k.startswith("apache/kafka#") for k in kafka.world.pull_requests)
    k8s = s.view("v1.38")
    assert not any(k.startswith("apache/") for k in k8s.world.pull_requests)
    assert sorted(s.current_release_keys()) == ["KAFKA:4.4.0", "kubernetes:v1.38"]


def test_kafka_release_and_feature_through_the_api() -> None:
    client = TestClient(create_app(service=service()))
    releases = {r["key"]: r for r in client.get("/releases").json()}
    kafka = releases["KAFKA:4.4.0"]
    assert kafka["display_name"] == "Apache Kafka"
    assert kafka["code_freeze_at"] is None  # Jira release dates only (ADR-0018)
    assert (kafka["features_in_release"], kafka["features_ever_in_release"]) == (1, 1)
    rows = client.get("/releases/4.4.0/features").json()["features"]
    assert [(r["key"], r["number"]) for r in rows] == [("KAFKA-20682", 20682)]
    assert rows[0]["prs_total"] == 2  # both roll up from the sub-task
    detail = client.get("/releases/4.4.0/features/20682")
    assert detail.status_code == 200
    assert client.get("/releases/4.4.0/features/20703").status_code == 404  # sub-task


def test_every_read_endpoint_copes_with_a_release_without_freeze_dates() -> None:
    client = TestClient(create_app(service=service()), raise_server_exceptions=False)
    paths = [
        "features",
        "features/20682",
        "summary",
        "graph",
        "dependencies",
        "merge-dates",
        "load",
        "simulator",
        "link-suggestions",
        "updates",
        "scenarios",
        "snapshots",
    ]
    codes = {p: client.get(f"/releases/4.4.0/{p}").status_code for p in paths}
    assert all(code < 500 for code in codes.values()), codes
