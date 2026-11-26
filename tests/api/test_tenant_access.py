"""Which tenant a request is for, and who may see it (ADR-0034, #231).

No header: the public demo, as before tenants. Another tenant needs a signed-in member and
a version 2 signature that covers the tenant. Nothing ever falls back to the demo.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.auth import AuthConfig, signature
from api.main import create_app
from api.tenants import MemoryDirectory, TenantInfo
from pipeline.store.tenancy import DEMO
from tests.api.test_auth import service

SECRET = b"test-secret"
REQUIRED = AuthConfig("required", SECRET, frozenset({"demo-approver"}))
DIRECTORY = MemoryDirectory(
    tenants={
        DEMO: TenantInfo(DEMO, "Public demo", True),
        "acme": TenantInfo("acme", "Acme", False),
        "globex": TenantInfo("globex", "Globex", False),
    },
    members={("acme", "ada"): "owner", ("acme", "rex"): "reader", ("globex", "gus"): "owner"},
)


def headers(user: str, method: str, path: str, body: bytes = b"", *, tenant: str | None,
            version: int = 2, signed_for: str | None = None) -> dict[str, str]:  # fmt: skip
    """A forwarded request for ``user``. ``signed_for`` signs for another tenant (replay)."""
    ts = str(int(time.time()))
    line = (signed_for or tenant or DEMO) if version == 2 else None
    out = {"x-tpm-user": user, "x-tpm-time": ts, "content-type": "application/json",
           "x-tpm-signature": signature(SECRET, user, ts, method, path, body, line)}  # fmt: skip
    if version == 2:
        out["x-tpm-signature-version"] = "2"
    if tenant is not None:
        out["x-tpm-tenant"] = tenant
    return out


@pytest.fixture(scope="module")
def api() -> TestClient:
    from agents.link_store import MemoryLinkSuggestionStore
    from api.sim_store import MemorySimStore

    return TestClient(create_app(service=service(), auth=REQUIRED, tenants=DIRECTORY,
                                 link_store=MemoryLinkSuggestionStore(),
                                 sim_store=MemorySimStore()))  # fmt: skip


def test_no_header_is_the_public_demo_as_before(api: TestClient) -> None:
    assert api.get("/raid/summary").status_code == 200
    assert api.get("/raid/summary", headers={"x-tpm-tenant": "demo"}).status_code == 200


def test_unknown_and_malformed_tenants_are_404(api: TestClient) -> None:
    for tenant in ("initech", "Not A Slug", "../demo"):
        res = api.get("/raid/summary", headers={"x-tpm-tenant": tenant})
        assert res.status_code == 404, tenant


def test_a_private_tenant_needs_sign_in(api: TestClient) -> None:
    res = api.get("/raid/summary", headers={"x-tpm-tenant": "acme"})
    assert res.status_code == 401


def test_a_non_member_learns_nothing(api: TestClient) -> None:
    res = api.get("/raid/summary", headers=headers("gus", "GET", "/raid/summary", tenant="acme"))
    assert res.status_code == 404
    assert res.json()["detail"] == "unknown tenant"  # the same answer as for no tenant at all


def test_a_member_reads_their_tenant(api: TestClient) -> None:
    me = api.get("/me", headers=headers("rex", "GET", "/me", tenant="acme"))
    assert me.status_code == 200
    assert me.json()["approver"] is False  # a reader
    owner = api.get("/me", headers=headers("ada", "GET", "/me", tenant="acme")).json()
    assert owner["approver"] is True


def test_a_version_1_signature_is_refused_for_a_private_tenant(api: TestClient) -> None:
    res = api.get("/me", headers=headers("ada", "GET", "/me", tenant="acme", version=1))
    assert res.status_code == 401


def test_a_signature_for_one_tenant_cannot_be_replayed_against_another(api: TestClient) -> None:
    res = api.get("/me", headers=headers("gus", "GET", "/me", tenant="acme", signed_for="globex"))
    assert res.status_code == 401


def test_roles_decide_actions_and_the_body_survives_the_check(api: TestClient) -> None:
    path, body = "/raid/4/reject", json.dumps({"reason": "not a risk"}).encode()
    reader = api.post(path, content=body, headers=headers("rex", "POST", path, body, tenant="acme"))
    assert reader.status_code == 403
    owner = api.post(path, content=body, headers=headers("ada", "POST", path, body, tenant="acme"))
    assert owner.status_code == 200, owner.text  # the endpoint still read the signed body
    assert owner.json()["review"] == "rejected"


def test_demo_approvers_are_not_approvers_of_a_private_tenant(api: TestClient) -> None:
    res = api.get("/me", headers=headers("demo-approver", "GET", "/me", tenant="acme"))
    assert res.status_code == 404


def test_the_demo_still_uses_the_allowlist_with_either_signature(api: TestClient) -> None:
    for version in (1, 2):
        res = api.get("/me", headers=headers("demo-approver", "GET", "/me", tenant=None,
                                             version=version))  # fmt: skip
        assert res.json()["approver"] is True, version


def test_a_directory_outage_is_503_never_the_demo() -> None:
    class Down(MemoryDirectory):
        def tenant(self, tenant_id: str) -> Any:
            raise RuntimeError("database is down")

    client = TestClient(create_app(service=service(), auth=REQUIRED, tenants=Down()))
    res = client.get("/raid/summary", headers={"x-tpm-tenant": "acme"})
    assert res.status_code == 503
    assert client.get("/raid/summary").status_code == 200  # the demo needs no directory
