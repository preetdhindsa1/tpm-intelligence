"""Confirmed RAID items as citable facts for the risk notes and the VP update (#180)."""

from __future__ import annotations

from dataclasses import replace

from agents.selection import feature_facts, raid_keys_for
from modules.raid.store import RaidItem
from verify.facts import FactKind, FactSheet
from verify.raid_facts import raid_facts

K6395 = "kubernetes/enhancements#6395"
BASE = RaidItem(1, "k1", "kubernetes:v1.38", "K8S", "risk", "Main PR may miss Code Freeze",
                "KEP-6395 still needs an approver.", "doc", "2026-11-18", owner="SIG Storage",
                links=(K6395,))  # fmt: skip


def items() -> list[RaidItem]:
    return [
        replace(BASE, review="confirmed", raid_id="K8S-R-001"),
        replace(
            BASE,
            item_id=2,
            key="k2",
            type="action",
            title="Chase docs",
            links=(),
            owner=None,
            review="edited",
            raid_id="K8S-A-001",
        ),
        replace(BASE, item_id=3, key="k3"),  # suggested: AI output, never a fact
        replace(
            BASE, item_id=4, key="k4", review="confirmed", raid_id="K8S-R-002", status="closed"
        ),
    ]


def test_only_confirmed_open_items_become_facts_keyed_by_raid_id() -> None:
    sheet = FactSheet(raid_facts(items()))
    assert sorted({k.split("::")[0] for k in sheet}) == ["raid:K8S-A-001", "raid:K8S-R-001"]
    assert sheet["raid:K8S-R-001::title"].value == "Main PR may miss Code Freeze"
    assert sheet["raid:K8S-R-001::feature"].value == K6395
    assert sheet["raid:K8S-R-001::type"].kind is FactKind.LABEL
    assert "raid:K8S-A-001::owner" not in sheet  # nobody owns it: no owner fact


def test_a_feature_sees_only_its_linked_items() -> None:
    sheet = FactSheet(raid_facts(items()))
    assert {k.split("::")[0] for k in raid_keys_for(sheet, K6395)} == {"raid:K8S-R-001"}
    assert raid_keys_for(sheet, "kubernetes/enhancements#1") == []
    assert len(raid_keys_for(sheet)) == len(sheet)


def test_feature_facts_include_linked_raid_items() -> None:
    from types import SimpleNamespace

    feature = SimpleNamespace(key=K6395, pull_requests=(), teams=())
    sheet = feature_facts(feature, FactSheet(raid_facts(items())))  # type: ignore[arg-type]
    assert "raid:K8S-R-001::title" in sheet
    assert "raid:K8S-A-001::title" not in sheet
