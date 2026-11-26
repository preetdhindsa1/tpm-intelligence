"""Connectors per tenant (ADR-0035, #233): read by members, changed by owners, isolated."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.auth import AuthConfig, signature
from api.main import create_app
from api.tenants import MemoryDirectory, TenantInfo
from connectors.store import MemoryTeamConfigStore
from pipeline.store.tenancy import DEMO
from tests.api.test_auth import service

SECRET = b"test-secret"
AUTH = AuthConfig("required", SECRET, frozenset())
DIRECTORY = MemoryDirectory(
    tenants={DEMO: TenantInfo(DEMO, "Public demo", True), "acme": TenantInfo("acme", "Acme", False),
             "globex": TenantInfo("globex", "Globex", False)},
    members={("acme", "ada"): "owner", ("acme", "rex"): "reader", ("globex", "gus"): "owner"},
)  # fmt: skip
WEB = {
    "id": "acme-web", "display_name": "Acme web", "project": "acme-web",
    "link_pack": "github_issue",
    "planning": {"source": "github", "repo": "acme/web"}, "code": {"repos": ["acme/web"]},
    "calendar": {"path": "connectors/teams/acme-web-calendar.yaml"},
    "secret_refs": {"github": "github-token"},
}  # fmt: skip


def h(user: str, method: str, path: str, body: bytes = b"", tenant: str = "acme") -> dict[str, str]:
    ts = str(int(time.time()))
    return {"x-tpm-user": user, "x-tpm-time": ts, "x-tpm-tenant": tenant,
            "x-tpm-signature-version": "2", "content-type": "application/json",
            "x-tpm-signature": signature(SECRET, user, ts, method, path, body, tenant)}  # fmt: skip


@pytest.fixture
def api() -> tuple[TestClient, dict[str, MemoryTeamConfigStore]]:
    stores: dict[str, MemoryTeamConfigStore] = {}
    app = create_app(
        service=service(), auth=AUTH, tenants=DIRECTORY,
        team_configs=lambda t: stores.setdefault(t, MemoryTeamConfigStore()),
    )  # fmt: skip
    return TestClient(app), stores


def put(client: TestClient, user: str, body: dict[str, Any], tenant: str = "acme") -> Any:
    path = f"/tenants/{tenant}/connectors/{body['id']}"
    raw = json.dumps(body).encode()
    return client.put(path, content=raw, headers=h(user, "PUT", path, raw, tenant))


def test_an_owner_adds_a_connector_and_a_member_reads_it(
    api: tuple[TestClient, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api
    monkeypatch.setenv("TENANT_ACME_GITHUB_TOKEN", "ghp_not_shown")
    res = put(client, "ada", WEB)
    assert res.status_code == 200, res.text
    assert res.json()["version"] == 1
    assert put(client, "ada", WEB).json()["version"] == 2
    path = "/tenants/acme/connectors"
    body = client.get(path, headers=h("rex", "GET", path)).json()
    (row,) = body["connectors"]
    assert row["config"]["id"] == "acme-web"
    assert row["secrets"] == [{"ref": "github-token", "name": "tenant-acme-github-token",
                               "found": True}]  # fmt: skip
    assert "ghp_not_shown" not in json.dumps(body)  # a secret value never leaves the API


def test_a_reader_cannot_change_connectors(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    assert put(client, "rex", WEB).status_code == 403


def test_another_tenants_connectors_are_not_found(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    put(client, "ada", WEB)
    path = "/tenants/acme/connectors"
    # gus is an owner of globex, asking for acme's path while acting in globex.
    res = client.get(path, headers=h("gus", "GET", path, tenant="globex"))
    assert res.status_code == 404
    mine = "/tenants/globex/connectors"
    other = client.get(mine, headers=h("gus", "GET", mine, tenant="globex"))
    assert other.json() == {"connectors": []}


def test_an_invalid_config_is_422_and_nothing_is_stored(api: tuple[TestClient, Any]) -> None:
    client, stores = api
    assert put(client, "ada", {**WEB, "code": {"repos": []}}).status_code == 422
    assert (
        put(client, "ada", {**WEB, "secret_refs": {"github": "ghp_" + "x" * 36}}).status_code == 422
    )
    assert stores.get("acme") is None or stores["acme"].list() == []


def test_the_demo_connectors_are_the_yaml_files_and_cannot_change(
    api: tuple[TestClient, Any],
) -> None:
    client, _ = api
    body = client.get("/tenants/demo/connectors").json()
    assert {"kubernetes", "kafka"} <= {c["team_id"] for c in body["connectors"]}
    path = "/tenants/demo/connectors/kubernetes"
    raw = json.dumps({**WEB, "id": "kubernetes"}).encode()
    res = client.put(path, content=raw, headers=h("ada", "PUT", path, raw, tenant=DEMO))
    assert res.status_code == 403


def test_delete(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    put(client, "ada", WEB)
    path = "/tenants/acme/connectors/acme-web"
    assert client.delete(path, headers=h("ada", "DELETE", path)).status_code == 204
    assert client.delete(path, headers=h("ada", "DELETE", path)).status_code == 404
