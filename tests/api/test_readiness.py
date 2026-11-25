"""Readiness and retro API on its synthetic fixture (docs/api/readiness-retro-contract.md)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.readiness import readiness_router

PATHS = ("/readiness", "/retro", "/retro/said-vs-showed", "/retro/patterns")


async def _anyone() -> str:
    return "approver"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(readiness_router(_anyone))
    return TestClient(app)


def test_every_response_says_it_is_synthetic(client: TestClient) -> None:
    for path in PATHS:
        assert client.get(path).json()["synthetic"] is True


def test_a_failing_criterion_makes_the_release_not_ready(client: TestClient) -> None:
    r = client.get("/readiness").json()
    assert r["verdict"] == "not_ready"
    assert r["validated"] is False


def test_decisions_need_a_note_and_are_only_appended(client: TestClient) -> None:
    url = "/readiness/v1.38/decision"
    assert client.post(url, json={"decision": "go"}).status_code == 422
    client.post(url, json={"decision": "no_go", "note": "two main PRs open"})
    after = client.post(url, json={"decision": "go", "note": "exceptions approved"}).json()
    assert [d["decision"] for d in after["decisions"]] == ["no_go", "go"]
    assert client.get("/readiness?release=v1.37").json()["decisions"] == []


def test_patterns_only_for_groups_of_ten(client: TestClient) -> None:
    p = client.get("/retro/patterns").json()
    assert p["min_group"] == 10
    assert all(x["n"] >= 10 for x in p["patterns"])
