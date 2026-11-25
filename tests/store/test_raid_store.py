"""PostgresRaidStore against a real, migrated database (migration 0010)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from modules.raid.postgres import PostgresRaidStore
from modules.raid.store import RaidItem, suggestion_key

pytestmark = pytest.mark.integration

AT = datetime(2026, 11, 25, 18, tzinfo=UTC)
DOC = "1fkUQyLupx_jkPcXtWmxnmVVVMj7KHRizx_yBRxJMOw0"


def item(quote: str, type_: str = "risk") -> RaidItem:
    key = suggestion_key(DOC, "2026-11-18", type_, quote)
    return RaidItem(0, key, "kubernetes:v1.38", "K8S", type_, quote[:40], quote, DOC,  # type: ignore[arg-type]
                    "2026-11-18")  # fmt: skip


@pytest.fixture
def store(engine: Engine) -> PostgresRaidStore:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE raid_history, raid_items RESTART IDENTITY"))
    return PostgresRaidStore(sessionmaker(engine))


def test_replay_ids_and_rejects_match_the_memory_store(store: PostgresRaidStore) -> None:
    a = store.suggest(item("Main PR for #6395 needs an approver"), AT)
    b = store.suggest(item("Docs PR for #6395 is missing", "action"), AT)
    c = store.suggest(item("Still no approver on the #6395 main PR"), AT)
    assert a
    assert b
    assert c
    assert store.suggest(item("Main PR for #6395 needs an approver"), AT) is None  # idempotent
    assert c.merge_into == a.item_id  # suggested only
    assert store.decide(a.item_id, "confirmed", "owner", AT).raid_id == "K8S-R-001"
    assert store.decide(c.item_id, "rejected", "owner", AT, reason="duplicate").raid_id is None
    assert store.decide(b.item_id, "edited", "owner", AT, {"owner": "SIG Docs"}).raid_id == (
        "K8S-A-001"
    )
    closed = store.decide(a.item_id, "edited", "owner", AT, {"status": "closed"})
    assert closed.raid_id == "K8S-R-001"
    assert [h.action for h in closed.history] == ["suggested", "confirmed", "edited"]
    assert store.suggest(item("Still no approver on the #6395 main PR"), AT) is None
    with pytest.raises(ValueError, match="rejected"):
        store.decide(c.item_id, "confirmed", "owner", AT)


def test_the_database_refuses_an_id_without_a_confirm(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE raid_history, raid_items RESTART IDENTITY"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO raid_items (key, release_key, workstream, type, title, quote, "
            "document_id, meeting_date, raid_id) VALUES ('k', 'r', 'K8S', 'risk', 't', 'q', "
            "'d', '2026-11-18', 'K8S-R-009')"))  # fmt: skip
