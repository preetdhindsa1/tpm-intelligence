"""RAID API on the real store (#180): contract shapes, release filter, no logins returned."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.raid import raid_router
from api.raid_store import StoreRaid
from modules.raid.store import MemoryRaidStore, RaidItem, suggestion_key

NOW = datetime(2026, 11, 25, 12, tzinfo=UTC)
DOC = "1fkUQyLupx_jkPcXtWmxnmVVVMj7KHRizx_yBRxJMOw0"
V138 = "kubernetes:v1.38"


@dataclass(frozen=True)
class Who:
    login: str = "an-approver"


async def _approver() -> Who:
    return Who()


def item(quote: str, type_: str = "issue", release: str = V138) -> RaidItem:
    key = suggestion_key(DOC, "2026-11-18", type_, quote)
    return RaidItem(0, key, release, "K8S", type_, "A title", quote, DOC, "2026-11-18",  # type: ignore[arg-type]
                    owner="Release Signal", links=("kubernetes/enhancements#6395",))  # fmt: skip


@pytest.fixture
def client() -> TestClient:
    store = MemoryRaidStore()
    store.suggest(item("KEP-6395 was removed at Code Freeze and needs an exception."), NOW)
    store.suggest(item("We will chase the remaining docs PRs this week.", "action"), NOW)
    store.suggest(
        item("Another release's item, not shown for v1.38.", release="kubernetes:v1.37"), NOW
    )
    titles = {DOC: "Kubernetes v1.38 Release Team Meeting"}
    app = FastAPI()
    app.include_router(raid_router(_approver, StoreRaid(lambda: store, titles, lambda: NOW)))
    return TestClient(app)


def test_real_items_are_not_synthetic_and_link_to_their_source(client: TestClient) -> None:
    queue = client.get("/raid/queue").json()
    assert queue["synthetic"] is False
    assert [i["type"] for i in queue["items"]] == ["issue", "action"]
    first = queue["items"][0]
    assert first["source"]["url"] == f"https://docs.google.com/document/d/{DOC}"
    assert first["source"]["title"] == "Kubernetes v1.38 Release Team Meeting, 2026-11-18"
    assert first["source"]["synthetic"] is False
    assert first["links"] == [
        {"kind": "feature", "ref": "kubernetes/enhancements#6395", "method": "explicit_key",
         "status": "verified"}
    ]  # fmt: skip
    assert client.get("/raid").json()["items"] == []  # nothing confirmed yet


def test_release_filter(client: TestClient) -> None:
    other = client.get("/raid/queue?release=v1.37").json()
    assert other["release"] == "v1.37"
    assert len(other["items"]) == 1
    assert client.get("/raid/summary").json()["waiting_for_review"] == 2


def test_confirm_gives_an_id_and_history_never_returns_the_login(client: TestClient) -> None:
    done = client.post("/raid/1/confirm", json={"note": "Checked against the notes."}).json()
    assert (done["review"], done["raid_id"]) == ("confirmed", "K8S-I-001")
    assert [i["raid_id"] for i in client.get("/raid").json()["items"]] == ["K8S-I-001"]
    history = client.get("/raid/1/history").json()
    assert [h["action"] for h in history["history"]] == ["suggested", "confirmed"]
    assert "an-approver" not in str(history)


def test_refusals_and_unknown_items(client: TestClient) -> None:
    assert client.post("/raid/2/reject", json={"reason": "Not a RAID item."}).status_code == 200
    assert client.post("/raid/2/confirm", json={}).status_code == 409
    assert client.get("/raid/99/history").status_code == 404
    assert client.post("/raid/99/confirm", json={}).status_code == 404


def test_summary_counts_the_notes_sources_for_the_release(client: TestClient) -> None:
    assert client.get("/raid/summary").json()["sources"] == 1  # the v1.38 meeting notes
    assert client.get("/raid/summary?release=v1.37").json()["sources"] == 1  # the retro doc
    none = client.get("/raid/summary?project=KAFKA&release=4.4.0").json()
    assert none["sources"] == 0  # nothing connected: zeros are not "no risks"
    assert none["waiting_for_review"] == 0
