"""Retro API on stored replays (#182): the real #6395 retro, said vs showed, min group 10."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.readiness import readiness_router
from api.retro_store import StoreRetro
from modules.raid.store import RaidItem
from modules.retro.facts import FeatureRow, RetroRun
from modules.retro.store import MemoryRetroStore
from tests.engine.conftest import K6395, V138, utc
from tests.modules.test_retro_facts import NOW, run


async def _approver() -> None:
    return None


SAID = RaidItem(7, "k7", V138, "K8S", "risk", "CI flakes before the freeze", "q", "doc",
                "2026-11-10")  # fmt: skip


def client(store: MemoryRetroStore) -> TestClient:
    app = FastAPI()
    retro = StoreRetro(lambda: store, lambda key: [SAID] if key == V138 else [])
    app.include_router(readiness_router(_approver, retro=retro))
    return TestClient(app)


def test_the_stored_retro_round_trips_and_is_not_synthetic() -> None:
    store = MemoryRetroStore()
    store.add(run())
    body = client(store).get("/retro", params={"release": "v1.38"}).json()
    assert (body["release"], body["synthetic"], body["sources"][0]["synthetic"]) == (
        "v1.38", False, False)  # fmt: skip
    six = next(s for s in body["slips"] if s["feature_key"] == K6395)
    assert (six["slip"], six["first_warning_flag"], six["lead_time_days"]) == (
        "late_exception", "ci_failing", 21.0)  # fmt: skip
    assert body["totals"]["warned_landed"] == 0
    assert client(MemoryRetroStore()).get("/retro?release=v1.38").status_code == 404


def test_said_vs_showed_puts_meeting_items_next_to_that_days_replay() -> None:
    store = MemoryRetroStore()
    store.add(run())
    [row] = client(store).get("/retro/said-vs-showed?release=v1.38").json()["rows"]
    assert row["date"].startswith("2026-11-10")
    assert row["said"][0]["review"] == "suggested"
    showed = {s["name"]: s["value"] for s in row["showed"]}
    assert showed["replay_day"] == "2026-11-10"
    assert showed["features_at_risk"] >= 1


def test_patterns_are_per_pool_and_small_groups_are_only_counted() -> None:
    rows = tuple(FeatureRow(f"f{i}", "sig/node" if i < 12 else "sig/apps", i < 3, ())
                 for i in range(15))  # fmt: skip
    store = MemoryRetroStore()
    store.add(RetroRun("kubernetes:v1.37", NOW, utc(2026, 7, 26), "retro-1", 15, (), 0, (), rows))
    store.add(RetroRun("KAFKA:4.4.0", NOW, NOW, "retro-1", 15, (), 0, (), rows))
    body = client(store).get("/retro/patterns?project=kubernetes").json()
    assert (body["min_group"], body["suppressed_groups"]) == (10, 1)
    assert {(p["pool"], p["pattern"], p["n"]) for p in body["patterns"]} == {
        ("sig/node", "slipped", 12), ("sig/node", "late_main_pr", 12)}  # fmt: skip
