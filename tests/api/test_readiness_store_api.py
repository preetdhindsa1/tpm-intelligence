"""Readiness API on real rules (#181): #6395's history, the decision log, no logins returned."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.readiness import readiness_router
from api.readiness_store import StoreReadiness, evidence_url
from engine.assess import assess_release
from engine.projection import project
from modules.raid.store import RaidItem
from modules.readiness.decisions import MemoryDecisionLog
from tests.engine.conftest import V138, fixture_events, utc

NOW = datetime(2026, 11, 26, 9, tzinfo=UTC)


@dataclass(frozen=True)
class Who:
    login: str = "an-approver"


async def _approver() -> Who:
    return Who()


async def _view(name: str) -> SimpleNamespace:
    if name != "v1.38":
        raise HTTPException(404, f"unknown release {name}")
    as_of = utc(2026, 11, 10)
    return SimpleNamespace(assessment=assess_release(project(fixture_events(), as_of), V138))


RISK = RaidItem(1, "k1", V138, "K8S", "risk", "CI flakes block the freeze", "quote", "doc",
                "2026-11-18", review="confirmed", raid_id="K8S-R-001")  # fmt: skip


def client(raid: object = lambda key: [RISK]) -> tuple[TestClient, MemoryDecisionLog]:
    log = MemoryDecisionLog()
    app = FastAPI()
    data = StoreReadiness(_view, raid, log)  # type: ignore[arg-type]
    app.include_router(readiness_router(_approver, lambda: NOW, data=data))
    return TestClient(app), log


def test_readiness_comes_from_the_rules_on_the_release_view() -> None:
    body = client()[0].get("/readiness", params={"release": "v1.38"}).json()
    assert (body["project"], body["release"], body["synthetic"]) == ("kubernetes", "v1.38", False)
    assert body["as_of"].startswith("2026-11-10")
    assert body["verdict"] == "not_ready"
    c = {c["id"]: c for c in body["criteria"]}
    assert c["code_merged"]["status"] == "fail"
    [ev] = c["code_merged"]["evidence"]
    assert ev["url"] == "https://github.com/kubernetes/enhancements/issues/6395"
    assert (c["risks_owned"]["status"], c["risks_owned"]["evidence"][0]["ref"]) == (
        "fail", "raid:K8S-R-001")  # fmt: skip
    assert c["docs_merged"]["status"] == "unknown"
    assert body["validated"] is False


def test_a_decision_is_appended_with_the_facts_seen_and_no_login() -> None:
    api, log = client()
    r = api.post("/readiness/v1.38/decision", json={"decision": "no_go", "note": "Main PR open."})
    assert r.status_code == 201
    [d] = r.json()["decisions"]
    assert (d["decided_by"], d["facts_as_of"][:10]) == ("approver", "2026-11-10")
    assert "an-approver" not in r.text
    assert [(x.by, x.verdict) for x in log.rows] == [("an-approver", "not_ready")]
    api.post("/readiness/v1.38/decision", json={"decision": "defer", "note": "Wait a day."})
    assert len(api.get("/readiness?release=v1.38").json()["decisions"]) == 2


def test_errors_unknown_release_short_note_and_a_raid_outage() -> None:
    api, _ = client()
    assert api.get("/readiness?release=v9.99").status_code == 404
    assert api.post("/readiness/v1.38/decision", json={"decision": "go", "note": "  "}
                    ).status_code == 422  # fmt: skip

    def down(key: str) -> list[RaidItem]:
        raise RuntimeError("database down")

    c = {c["id"]: c for c in client(down)[0].get("/readiness?release=v1.38").json()["criteria"]}
    assert (c["risks_owned"]["status"], c["risks_owned"]["detail"]) == (
        "unknown", "RAID items could not be read.")  # fmt: skip


@pytest.mark.parametrize(("ref", "url"), [
    ("pr:kubernetes/kubernetes#143709", "https://github.com/kubernetes/kubernetes/pull/143709"),
    ("raid:K8S-R-001", None), ("feature:KAFKA-19831", None)])  # fmt: skip
def test_evidence_urls(ref: str, url: str | None) -> None:
    assert evidence_url(ref) == url
