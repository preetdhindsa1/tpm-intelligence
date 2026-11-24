"""When "landed" is judged (#86): Code Freeze + 3 days, or the release + 3 days for Kafka.

KAFKA-20465 (KIP-892) is the real fixture: tagged 4.4.0, dropped from it on 2026-08-21,
three weeks after Feature Freeze (the engine's Code Freeze, 2026-07-30) and two months
before 4.4.0 shipped (2026-10-26). Judged at Code Freeze it "landed"; it did not ship.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from collectors.jira import normalize as n
from connectors import load_team
from connectors.load import release_plan
from engine.forecast import finished_releases, landed, outcome_cutoff, outcome_definition
from engine.projection import ReleaseInfo, project
from pipeline.events import NormalizedEvent
from tests.engine.conftest import utc
from tests.engine.synthetic import Stream
from tests.engine.test_kafka_world import BASE, NOW, load


def kafka_44(landed_at: str) -> list[NormalizedEvent]:
    out = n.release_events(
        load("versions_KAFKA.json"),
        ["4.4.0"],
        project="KAFKA",
        project_key="KAFKA",
        base_url=BASE,
        observed_at=NOW,
        plan=release_plan(load_team("kafka")),
        landed_at=landed_at,
    )
    issue = load("issue_KAFKA-20465.json")
    out.append(n.issue_snapshot(issue, project="KAFKA", base_url=BASE, observed_at=NOW))
    out += n.issue_history(issue, project="KAFKA", observed_at=NOW)
    return out


def test_a_feature_dropped_after_feature_freeze_did_not_land_when_judged_at_release() -> None:
    at_release = project(kafka_44("release"), NOW)
    release = at_release.releases["KAFKA:4.4.0"]
    assert release.outcome_at == datetime(2026, 10, 26, tzinfo=UTC)
    assert outcome_cutoff(release) == datetime(2026, 10, 29, tzinfo=UTC)
    assert landed(at_release.features["KAFKA-20465"], release) is False

    # The old judgement, still used for Kubernetes: in the release at Aug 2, so "landed".
    at_freeze = project(kafka_44("code_freeze"), NOW)
    old = at_freeze.releases["KAFKA:4.4.0"]
    assert old.outcome_at is None
    assert landed(at_freeze.features["KAFKA-20465"], old) is True


def test_kafka_judges_at_the_release_and_kubernetes_at_code_freeze() -> None:
    assert load_team("kafka").landed_at == "release"
    assert load_team("kubernetes").landed_at == "code_freeze"
    k8s = ReleaseInfo(
        "kubernetes:v1.38",
        "v1.38",
        None,
        None,
        datetime(2026, 11, 17, 12, tzinfo=UTC),
        datetime(2026, 12, 16, tzinfo=UTC),
    )
    assert outcome_cutoff(k8s) == datetime(2026, 11, 20, 12, tzinfo=UTC)
    assert outcome_definition(k8s) == "still in the release 3 days after Code Freeze"
    kafka = project(kafka_44("release"), NOW).releases["KAFKA:4.4.0"]
    assert outcome_definition(kafka) == "still in the release 3 days after it ships"


def test_a_release_calibrates_only_once_its_outcome_is_known() -> None:
    """Judged at the release, 4.2.0's outcome is known 3 days after it shipped (Feb 17).
    Before then, using it would score it on data from after the prediction point."""
    s = Stream(utc(2026, 11, 24))
    shipped = utc(2026, 2, 17)
    s.release(
        "4.2.0", utc(2025, 9, 2), utc(2025, 11, 20), shipped, project="KAFKA", outcome_at=shipped
    )
    s.release("4.3.0", shipped, utc(2026, 3, 19), utc(2026, 5, 22), project="KAFKA")
    world = project(s.events, utc(2026, 11, 24))
    assert finished_releases(world, shipped + timedelta(days=1), exclude="KAFKA:4.3.0") == []
    assert finished_releases(world, shipped + timedelta(days=3), exclude="KAFKA:4.3.0") == [
        "KAFKA:4.2.0"
    ]
    # Judged at Code Freeze, a release counts from the day it ships, as before.
    k8s = Stream(utc(2026, 11, 24))
    k8s.release("v1.37", utc(2026, 5, 18), utc(2026, 7, 23, 12), utc(2026, 8, 26))
    k8s.release("v1.38", utc(2026, 8, 31), utc(2026, 11, 17, 12), utc(2026, 12, 16))
    w = project(k8s.events, utc(2026, 11, 24))
    assert finished_releases(w, utc(2026, 8, 26), exclude="kubernetes:v1.38") == [
        "kubernetes:v1.37"
    ]
