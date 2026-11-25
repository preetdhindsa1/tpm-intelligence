"""RAID store rules (ADR-0030 addendum 2): stable IDs, no reuse, idempotent replay."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from modules.raid.store import (
    MemoryRaidStore,
    RaidItem,
    merge_reason,
    next_raid_id,
    suggestion_key,
)

AT = datetime(2026, 11, 25, 18, tzinfo=UTC)
DOC = "1fkUQyLupx_jkPcXtWmxnmVVVMj7KHRizx_yBRxJMOw0"


def item(quote: str, type_: str = "risk", date: str = "2026-11-18") -> RaidItem:
    return RaidItem(0, suggestion_key(DOC, date, type_, quote), "kubernetes:v1.38", "K8S",
                    type_, quote[:40], quote, DOC, date)  # type: ignore[arg-type]  # fmt: skip


def test_the_key_ignores_whitespace_only() -> None:
    assert item("a  b\n c").key == item("a b c").key
    assert item("a b c").key != item("a b c", type_="action").key
    assert item("a b c").key != item("a b c", date="2026-11-25").key


def test_replay_is_idempotent() -> None:
    store = MemoryRaidStore()
    notes = [item("CI is red on node e2e"), item("Docs PR missing for #6395", "action")]
    assert all(store.suggest(i, AT) for i in notes)
    assert [store.suggest(i, AT) for i in notes] == [None, None]
    assert len(store.items("kubernetes:v1.38")) == 2


def test_ids_are_given_on_confirm_kept_and_never_reused() -> None:
    store = MemoryRaidStore()
    a = store.suggest(item("Risk one about the freeze"), AT)
    b = store.suggest(item("Risk two about reviewers"), AT)
    c = store.suggest(item("Risk three about docs"), AT)
    assert a
    assert b
    assert c
    assert a.raid_id is None
    assert store.decide(a.item_id, "confirmed", "owner", AT).raid_id == "K8S-R-001"
    rejected = store.decide(b.item_id, "rejected", "owner", AT, reason="not a risk")
    assert rejected.raid_id is None
    assert store.decide(c.item_id, "edited", "owner", AT, {"owner": "SIG Docs"}).raid_id == (
        "K8S-R-002"
    )
    again = store.decide(a.item_id, "edited", "owner", AT, {"status": "closed"})
    assert again.raid_id == "K8S-R-001"  # never changed
    assert next_raid_id({"K8S-R-001", "K8S-R-007"}, "K8S", "risk") == "K8S-R-008"


def test_a_rejected_suggestion_is_never_suggested_again() -> None:
    store = MemoryRaidStore()
    a = store.suggest(item("Maybe a risk"), AT)
    assert a
    store.decide(a.item_id, "rejected", "owner", AT, reason="noise")
    assert store.suggest(item("Maybe a risk"), AT) is None
    with pytest.raises(ValueError, match="rejected"):
        store.decide(a.item_id, "confirmed", "owner", AT)


@pytest.mark.parametrize(
    ("action", "changes", "reason", "match"),
    [
        ("rejected", None, None, "reason"),
        ("suggested", None, None, "extractor"),
        ("edited", {"quote": "changed"}, None, "quote"),
    ],
)
def test_bad_decisions_are_refused(
    action: str, changes: dict[str, str] | None, reason: str | None, match: str
) -> None:
    store = MemoryRaidStore()
    a = store.suggest(item("Something"), AT)
    assert a
    with pytest.raises(ValueError, match=match):
        store.decide(a.item_id, action, "owner", AT, changes, reason)  # type: ignore[arg-type]


def test_history_is_append_only_and_keeps_the_login_for_audit() -> None:
    store = MemoryRaidStore()
    a = store.suggest(item("Something"), AT)
    assert a
    done = store.decide(a.item_id, "confirmed", "preetdhindsa1", AT, reason=None)
    assert [h.action for h in done.history] == ["suggested", "confirmed"]
    assert [h.actor for h in done.history] == ["extractor", "approver"]
    assert done.history[1].by == "preetdhindsa1"


def test_merge_is_only_suggested_with_a_reason() -> None:
    a = item("Main PR for #6395 needs an approver")
    b = item("Still no approver on the #6395 main PR", date="2026-11-25")
    assert merge_reason(b, a) == "Same risk and both mention #6395."
    assert merge_reason(replace(b, type="action"), a) is None
    store = MemoryRaidStore()
    first = store.suggest(a, AT)
    second = store.suggest(b, AT)
    assert first
    assert second
    assert second.merge_into == first.item_id
    assert second.review == "suggested"  # nothing merged by itself
