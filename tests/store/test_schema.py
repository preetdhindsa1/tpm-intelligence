"""Schema behaviour against real Postgres, using the CLAUDE.md section 11 fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, delete, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from pipeline.events import (
    ChangeAction,
    Source,
    SubjectKind,
    SubjectRef,
    WorkItemLabelChanged,
    WorkItemReleaseChanged,
    new_event,
)
from pipeline.store.events_repo import append_events, events_for_subject
from pipeline.store.models import (
    Base,
    EventRecord,
    Link,
    PullRequest,
    Release,
    Review,
    WorkItem,
    WorkItemRelation,
    WorkItemRelease,
)
from pipeline.store.queries import active_work_items
from tests.store.conftest import alembic_config

pytestmark = pytest.mark.integration


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)  # type: ignore[misc]


K8S_6395 = SubjectRef(
    kind=SubjectKind.WORK_ITEM, source=Source.GITHUB, external_key="kubernetes/enhancements#6395"
)


def _work_item(
    key: str, *, source: str = "github", type_: str = "feature", **kw: object
) -> WorkItem:
    defaults: dict[str, object] = {
        "title": key,
        "state": "open",
        "status_category": "in_progress",
        "created_at": utc(2026, 9, 18),
        "updated_at": utc(2026, 11, 21),
    }
    return WorkItem(source=source, external_key=key, type=type_, **{**defaults, **kw})


def _pr(number: int, **kw: object) -> PullRequest:
    defaults: dict[str, object] = {
        "title": f"PR {number}",
        "state": "open",
        "created_at": utc(2026, 11, 2),
        "updated_at": utc(2026, 11, 2),
    }
    return PullRequest(repo="kubernetes/kubernetes", number=number, **{**defaults, **kw})


# ---------------------------------------------------------------- migrations


def test_models_match_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models and migrations differ; run alembic autogenerate: {diff}"


def test_downgrade_to_base_and_upgrade_again(db_url: str) -> None:
    cfg = alembic_config(db_url)
    command.downgrade(cfg, "base")
    eng = create_engine(db_url)
    with eng.connect() as conn:
        tables = (
            conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
            .scalars()
            .all()
        )
    assert set(tables) <= {"alembic_version"}
    command.upgrade(cfg, "head")
    with eng.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM events")).scalar_one() == 0
    eng.dispose()


# ---------------------------------------------------------------- event log


def _k8s_6395_history() -> list:  # type: ignore[type-arg]
    """Real #6395 release/label changes around Code Freeze (GitHub issue events)."""
    removed = utc(2026, 11, 17, 12, 5, 57)
    readded = utc(2026, 11, 21, 0, 33, 55)
    return [
        new_event(
            source=Source.GITHUB,
            subject=K8S_6395,
            occurred_at=removed,
            payload=WorkItemReleaseChanged(
                action=ChangeAction.REMOVED, release_key="kubernetes:v1.38"
            ),
            identity=("kubernetes:v1.38", "removed", removed.isoformat()),
        ),
        new_event(
            source=Source.GITHUB,
            subject=K8S_6395,
            occurred_at=utc(2026, 11, 17, 12, 5, 58),
            payload=WorkItemLabelChanged(action=ChangeAction.ADDED, label="tracked/no"),
            identity=("tracked/no", "added", "2026-11-17T12:05:58Z"),
        ),
        new_event(
            source=Source.GITHUB,
            subject=K8S_6395,
            occurred_at=readded,
            payload=WorkItemReleaseChanged(
                action=ChangeAction.ADDED, release_key="kubernetes:v1.38"
            ),
            identity=("kubernetes:v1.38", "added", readded.isoformat()),
        ),
    ]


def test_append_events_is_idempotent(session: Session) -> None:
    history = _k8s_6395_history()
    assert append_events(session, history) == 3
    assert append_events(session, history) == 0  # redelivery / re-poll
    assert append_events(session, []) == 0
    assert len(events_for_subject(session, K8S_6395)) == 3


def test_as_of_only_returns_events_that_occurred_before(session: Session) -> None:
    append_events(session, list(reversed(_k8s_6395_history())))  # arrival order must not matter
    as_of = utc(2026, 11, 18)
    seen = events_for_subject(session, K8S_6395, as_of=as_of)
    assert [e.event_type for e in seen] == ["work_item.release_changed", "work_item.label_changed"]
    assert all(e.occurred_at < as_of for e in seen)
    # Boundary is strict: an event exactly at as_of is excluded.
    assert len(events_for_subject(session, K8S_6395, as_of=utc(2026, 11, 17, 12, 5, 57))) == 0


@pytest.mark.parametrize(
    "stmt",
    [
        update(EventRecord).values(event_type="tampered"),
        delete(EventRecord),
        text("TRUNCATE events"),
    ],
    ids=["update", "delete", "truncate"],
)
def test_event_log_is_append_only(session: Session, stmt: object) -> None:
    append_events(session, _k8s_6395_history())
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(stmt)  # type: ignore[call-overload]


# ---------------------------------------------------------------- releases


def test_work_item_in_many_releases_kafka_21181(session: Session) -> None:
    """KAFKA-21181: In Progress while tagged with released fix versions 4.0.0-4.3.0."""
    item = _work_item("KAFKA-21181", source="jira", type_="bug", state="In Progress")
    releases = [
        Release(source="jira", project="KAFKA", name=v)
        for v in ("4.0.0", "4.1.0", "4.2.0", "4.3.0")
    ]
    session.add_all([item, *releases])
    session.flush()
    for rel in releases:
        session.add(
            WorkItemRelease(work_item_id=item.id, release_id=rel.id, added_at=utc(2026, 1, 1))
        )
    session.flush()
    session.refresh(item)
    assert sorted(m.release.name for m in item.releases) == ["4.0.0", "4.1.0", "4.2.0", "4.3.0"]
    for rel in releases:
        assert [w.external_key for w in active_work_items(session, rel.id)] == ["KAFKA-21181"]


def test_removed_item_disappears_from_current_state_k8s_6395(session: Session) -> None:
    v138 = Release(
        source="github", project="kubernetes", name="v1.38", code_freeze_at=utc(2026, 11, 17, 12)
    )
    item = _work_item("kubernetes/enhancements#6395")
    other = _work_item("kubernetes/enhancements#1")
    session.add_all([v138, item, other])
    session.flush()
    membership = WorkItemRelease(
        work_item_id=item.id, release_id=v138.id, added_at=utc(2026, 9, 21, 20, 34, 45)
    )
    session.add_all(
        [
            membership,
            WorkItemRelease(work_item_id=other.id, release_id=v138.id, added_at=utc(2026, 9, 21)),
        ]
    )
    session.flush()

    membership.status, membership.removed_at = "removed", utc(2026, 11, 17, 12, 5, 57)
    session.flush()
    assert [w.external_key for w in active_work_items(session, v138.id)] == [
        "kubernetes/enhancements#1"
    ]

    membership.status, membership.removed_at = "active", None
    membership.added_at = utc(2026, 11, 21, 0, 33, 55)
    session.flush()
    assert len(active_work_items(session, v138.id)) == 2


def test_removed_status_requires_removed_at(session: Session) -> None:
    rel = Release(source="github", project="kubernetes", name="v1.38")
    item = _work_item("kubernetes/enhancements#6395")
    session.add_all([rel, item])
    session.flush()
    session.add(
        WorkItemRelease(
            work_item_id=item.id, release_id=rel.id, status="removed", added_at=utc(2026, 9, 21)
        )
    )
    with pytest.raises(IntegrityError, match="removed_at_matches_status"):
        session.flush()


# ---------------------------------------------------------------- hierarchy and relations


def test_parent_hierarchy_and_self_parent_rejected(session: Session) -> None:
    epic = _work_item("KAFKA-17789", source="jira", type_="epic")
    session.add(epic)
    session.flush()
    story = _work_item("KAFKA-19831", source="jira", type_="story", parent_id=epic.id)
    session.add(story)
    session.flush()
    session.refresh(story)
    assert story.parent is not None
    assert story.parent.external_key == "KAFKA-17789"

    story.parent_id = story.id
    with pytest.raises(IntegrityError, match="not_own_parent"):
        session.flush()


def test_work_item_relation_kafka_19831_links_17789(session: Session) -> None:
    a = _work_item("KAFKA-19831", source="jira", type_="story")
    b = _work_item("KAFKA-17789", source="jira", type_="story")
    session.add_all([a, b])
    session.flush()
    session.add(
        WorkItemRelation(
            from_id=a.id,
            to_id=b.id,
            kind="relates_to",
            status="verified",
            evidence={"jira_issuelink": "relates to"},
        )
    )
    session.flush()
    session.add(WorkItemRelation(from_id=a.id, to_id=a.id, kind="blocks", status="verified"))
    with pytest.raises(IntegrityError, match="no_self_relation"):
        session.flush()


def test_unknown_work_item_type_rejected(session: Session) -> None:
    session.add(_work_item("X-1", type_="theme"))
    with pytest.raises(IntegrityError, match="ck_work_items_type"):
        session.flush()


# ---------------------------------------------------------------- PRs and links


def test_merged_state_requires_merged_at(session: Session) -> None:
    session.add(_pr(143709, state="merged"))
    with pytest.raises(IntegrityError, match="merged_at_state"):
        session.flush()


def test_reviews_cascade_with_pr(session: Session) -> None:
    """Regression: ORM delete used to NULL reviews.pull_request_id instead of cascading."""
    pr = _pr(143709, state="merged", merged_at=utc(2026, 11, 20, 23, 28, 24))
    session.add(pr)
    session.flush()
    session.add(
        Review(
            pull_request_id=pr.id,
            external_id="r1",
            reviewer="a",
            state="approved",
            submitted_at=utc(2026, 11, 20),
        )
    )
    session.flush()
    session.delete(pr)
    session.flush()
    assert session.query(Review).count() == 0


@pytest.fixture
def pr_and_item(session: Session) -> tuple[PullRequest, WorkItem]:
    pr = _pr(143709)
    item = _work_item("kubernetes/enhancements#6395")
    session.add_all([pr, item])
    session.flush()
    return pr, item


def _link(pr: PullRequest, item: WorkItem, **kw: object) -> Link:
    defaults: dict[str, object] = {"confidence": Decimal("0.99"), "status": "verified"}
    return Link(pull_request_id=pr.id, work_item_id=item.id, **{**defaults, **kw})


def test_explicit_key_link_can_be_verified(
    session: Session, pr_and_item: tuple[PullRequest, WorkItem]
) -> None:
    pr, item = pr_and_item
    session.add(
        _link(pr, item, method="explicit_key", evidence={"field": "body", "match": "KEP-6395"})
    )
    session.flush()


def test_ai_link_cannot_be_verified_without_a_verifier(
    session: Session, pr_and_item: tuple[PullRequest, WorkItem]
) -> None:
    pr, item = pr_and_item
    session.add(_link(pr, item, method="ai_suggested", confidence=Decimal("0.7")))
    with pytest.raises(IntegrityError, match="ai_links_need_verifier"):
        session.flush()


def test_ai_link_suggested_then_confirmed_by_person(
    session: Session, pr_and_item: tuple[PullRequest, WorkItem]
) -> None:
    pr, item = pr_and_item
    link = _link(pr, item, method="ai_suggested", confidence=Decimal("0.7"), status="suggested")
    session.add(link)
    session.flush()
    link.status, link.verified_by, link.verified_at = "verified", "user:tpm", utc(2026, 11, 21)
    session.flush()


@pytest.mark.parametrize("confidence", [Decimal("-0.01"), Decimal("1.001")])
def test_confidence_must_be_between_0_and_1(
    session: Session, pr_and_item: tuple[PullRequest, WorkItem], confidence: Decimal
) -> None:
    pr, item = pr_and_item
    session.add(_link(pr, item, method="labels", confidence=confidence))
    with pytest.raises((IntegrityError, DBAPIError)):
        session.flush()


def test_unknown_link_method_rejected(
    session: Session, pr_and_item: tuple[PullRequest, WorkItem]
) -> None:
    pr, item = pr_and_item
    session.add(_link(pr, item, method="vibes"))
    with pytest.raises(IntegrityError, match="ck_links_method"):
        session.flush()
