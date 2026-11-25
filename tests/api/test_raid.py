"""RAID API on its synthetic fixture (Wave 4 contract, docs/api/raid-contract.md)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.raid import FixtureRaid, raid_router


async def _anyone() -> str:
    return "approver"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(raid_router(_anyone, FixtureRaid()))
    return TestClient(app)


def test_every_response_says_it_is_synthetic(client: TestClient) -> None:
    for path in ("/raid", "/raid/queue", "/raid/summary", "/raid/1/history"):
        assert client.get(path).json()["synthetic"] is True
    assert all(i["source"]["synthetic"] for i in client.get("/raid").json()["items"])


def test_tracker_and_queue_split_by_review(client: TestClient) -> None:
    tracker = client.get("/raid").json()["items"]
    queue = client.get("/raid/queue").json()["items"]
    assert {i["review"] for i in tracker} == {"confirmed", "edited"}
    assert {i["review"] for i in queue} == {"suggested"}
    assert all(i["raid_id"] is None for i in queue)


def test_confirm_gives_the_next_id_and_records_history(client: TestClient) -> None:
    item = client.post("/raid/4/confirm", json={}).json()
    assert item["raid_id"] == "K8S-R-002"  # K8S-R-001 is taken
    assert item["review"] == "confirmed"
    again = client.post("/raid/4/edit", json={"owner": "SIG Node"}).json()
    assert again["raid_id"] == "K8S-R-002"  # never changed
    actions = [h["action"] for h in client.get("/raid/4/history").json()["history"]]
    assert actions == ["suggested", "confirmed", "edited"]


def test_reject_needs_a_reason_and_gives_no_id(client: TestClient) -> None:
    assert client.post("/raid/5/reject", json={}).status_code == 422
    item = client.post("/raid/5/reject", json={"reason": "duplicate of item 4"}).json()
    assert item["raid_id"] is None
    assert client.post("/raid/5/confirm", json={}).status_code == 409
    assert client.post("/raid/99/confirm", json={}).status_code == 404


def test_the_quote_cannot_be_edited(client: TestClient) -> None:
    before = client.get("/raid/queue").json()["items"][0]
    after = client.post(f"/raid/{before['item_id']}/edit", json={"quote": "changed"}).json()
    assert after["quote"] == before["quote"]


def test_summary_counts(client: TestClient) -> None:
    s = client.get("/raid/summary").json()
    risk = next(r for r in s["by_type"] if r["type"] == "risk")
    assert (risk["suggested"], risk["open"]) == (2, 1)
    assert s["waiting_for_review"] == 2
    assert s["risks_without_owner"] == 0
    client.post("/raid/4/confirm", json={})  # a confirmed risk with no owner
    assert client.get("/raid/summary").json()["risks_without_owner"] == 1
