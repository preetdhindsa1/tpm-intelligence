"""Tenants, members, limits, audit, export and deletion over the API (ADR-0035, #234)."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.auth import AuthConfig, signature
from api.main import create_app
from api.tenants import MemoryDirectory, TenantInfo
from connectors.admin import Limits, MemoryTenantAdmin
from pipeline.store.tenancy import DEMO
from tests.api.test_auth import service

SECRET = b"test-secret"
AUTH = AuthConfig("required", SECRET, frozenset())


def h(user: str, method: str, path: str, body: bytes = b"", tenant: str = DEMO) -> dict[str, str]:
    ts = str(int(time.time()))
    out = {"x-tpm-user": user, "x-tpm-time": ts, "x-tpm-signature-version": "2",
           "content-type": "application/json",
           "x-tpm-signature": signature(SECRET, user, ts, method, path, body, tenant)}  # fmt: skip
    if tenant != DEMO:
        out["x-tpm-tenant"] = tenant
    return out


class Directory(MemoryDirectory):
    """The tenant directory reads the same in-memory admin, as Postgres would."""

    def __init__(self, admin: MemoryTenantAdmin) -> None:
        super().__init__()
        self.admin = admin

    def tenant(self, tenant_id: str) -> TenantInfo | None:
        if tenant_id == DEMO:
            return TenantInfo(DEMO, "Public demo", True)
        t = self.admin.tenants.get(tenant_id)
        return TenantInfo(tenant_id, t[0], t[1]) if t else None

    def role(self, tenant_id: str, login: str) -> str | None:
        hit = self.admin.roles.get((tenant_id, login.lower()))
        return hit[0] if hit else None


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, MemoryTenantAdmin]:
    monkeypatch.setenv("TENANT_CREATORS", "ada")
    admin = MemoryTenantAdmin()
    app = create_app(service=service(), auth=AUTH, tenants=Directory(admin), tenant_admin=admin)
    return TestClient(app), admin


def call(client: TestClient, method: str, user: str, path: str, body: Any = None,
         tenant: str = DEMO) -> Any:  # fmt: skip
    raw = json.dumps(body).encode() if body is not None else b""
    return client.request(method, path, content=raw or None,
                          headers=h(user, method, path, raw, tenant))  # fmt: skip


def test_create_list_and_only_creators_may_create(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    assert (
        call(client, "POST", "rex", "/tenants", {"id": "acme", "name": "Acme"}).status_code == 403
    )
    res = call(client, "POST", "ada", "/tenants", {"id": "acme", "name": "Acme"})
    assert res.status_code == 201
    assert res.json()["role"] == "owner"
    assert call(client, "POST", "ada", "/tenants", {"id": "acme", "name": "x"}).status_code == 409
    for reserved in ("demo", "system", "Not Slug"):
        res = call(client, "POST", "ada", "/tenants", {"id": reserved, "name": "x"})
        assert res.status_code == 422, reserved
    mine = call(client, "GET", "ada", "/me/tenants").json()
    assert [t["id"] for t in mine["tenants"]] == ["demo", "acme"]
    assert mine["can_create"] is True
    assert client.get("/me/tenants").status_code == 401


def test_members_roles_and_the_last_owner(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    call(client, "POST", "ada", "/tenants", {"id": "acme", "name": "Acme"})
    p = "/tenants/acme/members/rex"
    assert call(client, "PUT", "ada", p, {"role": "reader"}, "acme").status_code == 200
    assert call(client, "PUT", "rex", "/tenants/acme/members/ada", {"role": "reader"},
                "acme").status_code == 403  # fmt: skip
    last = call(client, "PUT", "ada", "/tenants/acme/members/ada", {"role": "reader"}, "acme")
    assert last.status_code == 409  # an organization keeps at least one owner
    assert call(client, "PUT", "ada", p, {"role": "admin"}, "acme").status_code == 422
    listed = call(client, "GET", "ada", "/tenants/acme/members", tenant="acme").json()
    assert [(m["login"], m["role"]) for m in listed["members"]] == [("ada", "owner"),
                                                                    ("rex", "reader")]  # fmt: skip
    assert call(client, "DELETE", "ada", p, tenant="acme").status_code == 204
    audit = call(client, "GET", "ada", "/tenants/acme/audit", tenant="acme").json()["entries"]
    assert [e["action"] for e in audit] == ["member_removed", "member_role_set",
                                            "tenant_created"]  # fmt: skip
    assert all(e["actor"] == "owner" for e in audit)  # roles, never logins
    assert "ada" not in json.dumps([e["actor"] for e in audit])


def test_limits(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    call(client, "POST", "ada", "/tenants", {"id": "acme", "name": "Acme"})
    got = call(client, "GET", "ada", "/tenants/acme/limits", tenant="acme").json()
    assert got == {"ai_daily_budget_usd": 0.5, "max_teams": 3, "teams": 0}
    bad = {"ai_daily_budget_usd": 500, "max_teams": 3}
    assert call(client, "PUT", "ada", "/tenants/acme/limits", bad, "acme").status_code == 422
    ok = {"ai_daily_budget_usd": 1.25, "max_teams": 5}
    assert call(client, "PUT", "ada", "/tenants/acme/limits", ok, "acme").json() == ok


def test_export_and_delete(api: tuple[TestClient, Any]) -> None:
    client, admin = api
    call(client, "POST", "ada", "/tenants", {"id": "acme", "name": "Acme"})
    out = call(client, "POST", "ada", "/tenants/acme/export", tenant="acme")
    assert out.status_code == 200
    rows = [json.loads(line) for line in out.text.splitlines()]
    assert {r["row"]["tenant_id"] for r in rows} == {"acme"}
    wrong = call(client, "DELETE", "ada", "/tenants/acme", {"confirm": "nope"}, "acme")
    assert wrong.status_code == 422
    assert (
        call(client, "DELETE", "ada", "/tenants/acme", {"confirm": "acme"}, "acme").status_code
        == 204
    )
    assert "acme" not in admin.tenants
    assert [(t, e.action) for t, e in admin.log] == [("system", "tenant_deleted")]
    # Gone: the next request for it is an unknown tenant.
    assert call(client, "GET", "ada", "/tenants/acme/limits", tenant="acme").status_code == 404


def test_the_demo_cannot_be_administered(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    assert call(client, "DELETE", "ada", "/tenants/demo", {"confirm": "demo"}).status_code == 403
    assert call(client, "GET", "ada", "/tenants/demo/members").status_code == 403


def test_the_gateway_uses_the_tenants_cap() -> None:
    from agents.gateway import Gateway
    from agents.ledger import MemoryLedger
    from agents.settings import AISettings

    gw = Gateway(AISettings(), MemoryLedger(), cap=lambda: 0.25)
    assert gw.daily_cap() == 0.25
    assert Gateway(AISettings(), MemoryLedger()).daily_cap() == AISettings().daily_budget_usd


def test_limits_are_kept_per_tenant() -> None:
    admin = MemoryTenantAdmin(tenants={"acme": ("Acme", False, Limits(0.5, 3))})
    assert admin.limits("acme").ai_daily_budget_usd == 0.5
