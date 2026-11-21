"""Normalized event schema: round-trips, deterministic IDs, strict timestamps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from pipeline.events import (
    ChangeAction,
    CheckCompleted,
    CheckConclusion,
    EventPayload,
    NormalizedEvent,
    PullRequestObserved,
    ReferenceObserved,
    ReleaseObserved,
    ReviewState,
    ReviewSubmitted,
    Source,
    SubjectKind,
    SubjectRef,
    WorkItemLabelChanged,
    WorkItemObserved,
    WorkItemReleaseChanged,
    WorkItemSpecObserved,
    WorkItemStatusChanged,
    WorkItemType,
    make_event_id,
    new_event,
)

T = datetime(2026, 11, 17, 12, 5, 57, tzinfo=UTC)
KEP = SubjectRef(
    kind=SubjectKind.WORK_ITEM, source=Source.GITHUB, external_key="kubernetes/enhancements#6395"
)
PR = SubjectRef(
    kind=SubjectKind.PULL_REQUEST, source=Source.GITHUB, external_key="kubernetes/kubernetes#143709"
)

# One real-shaped example per payload type (values from the #6395 / v1.38 fixtures).
PAYLOADS: list[tuple[SubjectRef, EventPayload]] = [
    (
        KEP,
        WorkItemObserved(
            item_type=WorkItemType.FEATURE,
            title="Dynamic node-local ephemeral volumes",
            state="open",
            status_category="in_progress",
            labels=("sig/node", "sig/storage", "stage/alpha", "tracked/yes", "lead-opted-in"),
            release_keys=("kubernetes:v1.38",),
            created_at=datetime(2026, 9, 18, 18, 3, 25, tzinfo=UTC),
            updated_at=T,
        ),
    ),
    (
        KEP,
        WorkItemSpecObserved(
            spec_path="keps/sig-storage/6395-dynamic-node-local-ephemeral-volumes/kep.yaml",
            feature_flags=("DynamicNodeLocalEphemeralVolumes",),
            owning_team="sig-storage",
            participating_teams=("sig-node",),
            stage="alpha",
            target_release_key="kubernetes:v1.38",
            spec_status="implementable",
        ),
    ),
    (KEP, WorkItemReleaseChanged(action=ChangeAction.REMOVED, release_key="kubernetes:v1.38")),
    (KEP, WorkItemLabelChanged(action=ChangeAction.ADDED, label="tracked/no")),
    (KEP, WorkItemStatusChanged(from_state="open", to_state="closed", to_category="done")),
    (KEP, ReferenceObserved(pull_request=PR, evidence="remote_link")),
    (
        PR,
        PullRequestObserved(
            repo="kubernetes/kubernetes",
            number=143709,
            title="Dynamic node-local ephemeral volumes: alpha implementation",
            body="KEP: https://github.com/kubernetes/enhancements/issues/6395",
            state="merged",
            created_at=datetime(2026, 11, 2, 16, 44, 28, tzinfo=UTC),
            updated_at=datetime(2026, 11, 20, 23, 28, 24, tzinfo=UTC),
            merged_at=datetime(2026, 11, 20, 23, 28, 24, tzinfo=UTC),
        ),
    ),
    (
        PR,
        ReviewSubmitted(
            review_id="r1", reviewer="reviewer-a", state=ReviewState.APPROVED, submitted_at=T
        ),
    ),
    (
        PR,
        CheckCompleted(
            check_name="pull-kubernetes-unit",
            head_sha="abc123",
            conclusion=CheckConclusion.FAILURE,
            completed_at=T,
        ),
    ),
    (
        SubjectRef(kind=SubjectKind.RELEASE, source=Source.GITHUB, external_key="v1.38"),
        ReleaseObserved(
            project="kubernetes",
            name="v1.38",
            enhancements_freeze_at=datetime(2026, 9, 30, 12, tzinfo=UTC),
            code_freeze_at=datetime(2026, 11, 17, 12, tzinfo=UTC),
            release_at=datetime(2026, 12, 16, tzinfo=UTC),
        ),
    ),
]


@pytest.mark.parametrize(("subject", "payload"), PAYLOADS, ids=lambda p: getattr(p, "type", ""))
def test_every_payload_round_trips(subject: SubjectRef, payload: EventPayload) -> None:
    event = new_event(
        source=Source.GITHUB, subject=subject, occurred_at=T, payload=payload, identity=("x",)
    )
    restored = NormalizedEvent.from_bytes(event.to_bytes())
    assert restored == event
    assert type(restored.payload) is type(payload)
    assert restored.event_type == payload.type


def test_event_id_is_deterministic_and_identity_sensitive() -> None:
    payload = WorkItemLabelChanged(action=ChangeAction.ADDED, label="tracked/no")
    a = new_event(
        source=Source.GITHUB,
        subject=KEP,
        occurred_at=T,
        payload=payload,
        identity=("tracked/no", "added", T.isoformat()),
    )
    b = new_event(
        source=Source.GITHUB,
        subject=KEP,
        occurred_at=T,
        payload=payload,
        identity=("tracked/no", "added", T.isoformat()),
        observed_at=T + timedelta(days=1),
    )
    c = new_event(
        source=Source.GITHUB,
        subject=KEP,
        occurred_at=T,
        payload=payload,
        identity=("tracked/no", "added", (T + timedelta(seconds=1)).isoformat()),
    )
    assert a.event_id == b.event_id  # re-polled later: same fact, same ID
    assert a.event_id != c.event_id
    assert make_event_id(Source.GITHUB, "t", "k") != make_event_id(Source.JIRA, "t", "k")


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError):
        new_event(
            source=Source.GITHUB,
            subject=KEP,
            occurred_at=datetime(2026, 11, 17, 12, 5, 57),  # deliberately naive
            payload=WorkItemLabelChanged(action=ChangeAction.ADDED, label="tracked/no"),
            identity=(),
        )


def test_timestamps_are_normalized_to_utc() -> None:
    pacific = timezone(timedelta(hours=-8))
    event = new_event(
        source=Source.GITHUB,
        subject=KEP,
        occurred_at=datetime(2026, 11, 17, 4, 5, 57, tzinfo=pacific),
        payload=WorkItemLabelChanged(action=ChangeAction.ADDED, label="tracked/no"),
        identity=(),
    )
    assert event.occurred_at == T
    assert event.occurred_at.tzinfo == UTC


def test_unknown_fields_and_types_are_rejected() -> None:
    good = new_event(
        source=Source.GITHUB,
        subject=KEP,
        occurred_at=T,
        payload=WorkItemLabelChanged(action=ChangeAction.ADDED, label="x"),
        identity=(),
    ).model_dump(mode="json")
    with pytest.raises(ValidationError):
        NormalizedEvent.model_validate({**good, "surprise": 1})
    with pytest.raises(ValidationError):
        NormalizedEvent.model_validate({**good, "payload": {**good["payload"], "type": "nope"}})


def test_events_are_immutable() -> None:
    event = new_event(
        source=Source.GITHUB,
        subject=KEP,
        occurred_at=T,
        payload=WorkItemLabelChanged(action=ChangeAction.ADDED, label="x"),
        identity=(),
    )
    with pytest.raises(ValidationError):
        event.event_id = "other"  # type: ignore[misc]
