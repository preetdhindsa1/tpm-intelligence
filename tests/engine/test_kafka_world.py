"""Kafka through the engine, built from the real Jira fixtures (ADR-0018).

KAFKA-20682: New Feature umbrella in 4.4.0, KIP-1356, 8 sub-tasks.
KAFKA-20703: its sub-task, remote-linked to apache/kafka#22666.
KAFKA-19831 / KAFKA-21181: bugs, so load but not release features.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collectors.jira import normalize as n
from engine.links import link_release
from engine.projection import Feature, key_number, project
from linker.methods import LinkMethod, LinkStatus
from pipeline.events import (
    NormalizedEvent,
    PullRequestObserved,
    Source,
    SubjectKind,
    SubjectRef,
    new_event,
)

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "jira"
NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)
BASE = "https://issues.apache.org/jira"
R44 = "KAFKA:4.4.0"
# Remote links are dated when the collector saw them (Jira does not say when they were
# made), so they only count in worlds projected after that.
LATER = datetime(2026, 11, 22, 12, 1, tzinfo=UTC)


def load(name: str) -> Any:
    return json.loads((FIX / name).read_text())


def pr(number: int, title: str, created: datetime) -> NormalizedEvent:
    payload = PullRequestObserved(
        repo="apache/kafka",
        number=number,
        title=title,
        state="merged",
        created_at=created,
        updated_at=created,
        merged_at=created,
    )
    return new_event(
        source=Source.GITHUB,
        subject=SubjectRef(
            kind=SubjectKind.PULL_REQUEST,
            source=Source.GITHUB,
            external_key=f"apache/kafka#{number}",
        ),
        occurred_at=created,
        observed_at=NOW,
        payload=payload,
        identity=(number,),
    )


def events() -> list[NormalizedEvent]:
    out: list[NormalizedEvent] = []
    out += n.release_events(
        load("versions_KAFKA.json"),
        ["4.4.0"],
        project="KAFKA",
        project_key="KAFKA",
        base_url=BASE,
        observed_at=NOW,
    )
    for key in ("KAFKA-20682", "KAFKA-20703", "KAFKA-19831", "KAFKA-21181"):
        issue = load(f"issue_{key}.json")
        links = load(f"remotelinks_{key}.json")
        out.append(n.issue_snapshot(issue, project="KAFKA", base_url=BASE, observed_at=NOW))
        out += n.issue_history(issue, project="KAFKA", observed_at=NOW)
        out += n.remote_link_events(key, links, observed_at=NOW)
        spec = n.issue_spec(issue, links, observed_at=NOW)
        if spec:
            out.append(spec)
    # #22666 is remote-linked from the sub-task; #99999 names the sub-task in its title.
    out.append(
        pr(22666, "Implement TimestampedKeyWithHeadersQuery", datetime(2026, 7, 1, tzinfo=UTC))
    )
    out.append(pr(99999, "KAFKA-20703: follow-up", datetime(2026, 7, 2, tzinfo=UTC)))
    return out


def test_jira_keys_have_numbers() -> None:
    assert key_number("KAFKA-19831") == 19831
    assert key_number("kubernetes/enhancements#6395") == 6395


def test_only_features_umbrellas_and_kips_are_release_features() -> None:
    world = project(events(), LATER)
    assert set(world.features) >= {"KAFKA-20682", "KAFKA-20703", "KAFKA-19831"}
    assert [f.key for f in world.features_ever_in(R44)] == ["KAFKA-20682"]
    umbrella = world.features["KAFKA-20682"]
    assert umbrella.spec_path == "KIP-1356"
    assert umbrella.is_release_feature
    assert not world.features["KAFKA-20703"].is_release_feature  # sub-task
    assert not world.features["KAFKA-19831"].is_release_feature  # bug, no KIP
    assert [f.key for f in world.sub_items("KAFKA-20682")] == ["KAFKA-20703"]


def test_sub_task_prs_roll_up_to_the_umbrella() -> None:
    world = project(events(), LATER)
    links = link_release(world, R44, link_pack="jira_key")
    remote = links.best[("apache/kafka#22666", "KAFKA-20682")]
    assert remote.method is LinkMethod.REMOTE_LINK
    assert remote.status is LinkStatus.VERIFIED
    assert remote.evidence["via_sub_task"] == "KAFKA-20703"
    named = links.best[("apache/kafka#99999", "KAFKA-20682")]
    assert named.method is LinkMethod.EXPLICIT_KEY
    assert named.status is LinkStatus.VERIFIED
    assert links.verified_prs("KAFKA-20682") == ["apache/kafka#22666", "apache/kafka#99999"]
    # Nothing links to the sub-task itself.
    assert not any(item == "KAFKA-20703" for _, item in links.best)


def test_remote_links_do_not_leak_into_earlier_worlds() -> None:
    world = project(events(), NOW)
    assert world.references == ()


def test_release_has_jira_dates_only() -> None:
    r = project(events(), LATER).releases[R44]
    assert r.release_at == datetime(2026, 10, 26, tzinfo=UTC)
    assert r.code_freeze_at is None


def _item(item_type: str, title: str, spec: str | None, source: str | None) -> Feature:
    return Feature(
        key="KAFKA-1",
        number=1,
        title=title,
        url=None,
        description="",
        labels=frozenset(),
        release_keys=frozenset(),
        membership=(),
        label_history=(),
        item_type=item_type,
        spec_path=spec,
        spec_source=source,
    )


def test_kip_counts_only_in_the_title_or_a_link_and_never_for_bugs() -> None:
    """Shapes measured in 4.4.0 (2026-11-23); the description-only rule admitted 22 bugs."""
    # KAFKA-20032 "KIP-1265 : Mechanism for automatic detection of internal API usage"
    assert _item("story", "KIP-1265 : Mechanism", "KIP-1265", "title").is_release_feature
    assert _item("story", "Implement KIP 1340: keys", "KIP-1340", None).is_release_feature
    assert _item("story", "Rack-aware partitioning", "KIP-1123", "remote_link").is_release_feature
    # KAFKA-19193: KIP only in the description.
    assert not _item(
        "story", "Rack-aware partitioning", "KIP-1123", "description"
    ).is_release_feature
    # KAFKA-20253: a bug that mentions KIP-848; KAFKA-20663: a bug with the KIP in its title.
    assert not _item(
        "bug", "High CPU loop on consumer", "KIP-848", "description"
    ).is_release_feature
    assert not _item(
        "bug", "KIP-1035: stale changelog offset", "KIP-1035", "title"
    ).is_release_feature
    # New Features count with or without a KIP.
    assert _item("feature", "Dead-letter queues for share groups", None, None).is_release_feature
