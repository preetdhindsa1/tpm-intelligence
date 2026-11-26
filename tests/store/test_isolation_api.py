"""Every GET endpoint, as two tenants: neither sees the other's data (ADR-0034, #232).

The demo holds the real #6395 / v1.38 fixture. Acme holds one synthetic release, v9.99,
with feature #700 and "PR 9001". The API runs on real Postgres as a non-superuser role, so
row-level security is in force, with the tenant directory in the same database.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from api.auth import AuthConfig, signature
from api.tenants import PostgresDirectory
from pipeline.store.events_repo import append_events
from pipeline.store.models import Member
from pipeline.store.tenancy import use_tenant
from tests.engine.conftest import fixture_events, utc
from tests.engine.synthetic import Stream

pytestmark = pytest.mark.integration

SECRET = b"isolation-secret"
AUTH = AuthConfig("required", SECRET, frozenset())
DEMO_MARKERS = ("6395", "143709", "Dynamic node-local")
ACME_MARKERS = ("v9.99", "PR 9001", "F700")
PATH_VALUES = {"demo": {"name": "v1.38", "number": "6395"},
               "acme": {"name": "v9.99", "number": "700"}}  # fmt: skip
SKIP = {"/releases/{name}/stream"}  # server-sent events: an open stream, checked elsewhere


def _acme_events() -> list[Any]:
    s = Stream(utc(2026, 11, 26))
    key = s.release("v9.99", utc(2026, 9, 1), utc(2026, 11, 17, 12), utc(2026, 12, 16))
    s.feature(700, key, [(utc(2026, 9, 10), True)])
    s.pr(9001, 700, utc(2026, 10, 1))
    return s.events


@pytest.fixture(scope="module")
def client(app_engine: Engine, monkeypatch_module: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from api.main import create_app

    factory = sessionmaker(app_engine)
    for tenant, events in (("demo", list(fixture_events())), ("acme", _acme_events())):
        with use_tenant(tenant), factory() as s, s.begin():
            append_events(s, events)
    with use_tenant("acme"), factory() as s, s.begin():
        s.merge(Member(tenant_id="acme", login="ada", role="owner"))
    # The default stores read DATABASE_URL: point them at the non-superuser role.
    monkeypatch_module.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    app = create_app(auth=AUTH, tenants=PostgresDirectory(factory))
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def monkeypatch_module() -> Iterator[pytest.MonkeyPatch]:
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def _as(tenant: str, path: str) -> dict[str, str]:
    if tenant == "demo":
        return {}
    ts = str(int(time.time()))
    return {"x-tpm-tenant": tenant, "x-tpm-user": "ada", "x-tpm-time": ts,
            "x-tpm-signature-version": "2",
            "x-tpm-signature": signature(SECRET, "ada", ts, "GET", path, b"", tenant)}  # fmt: skip


def _paths(client: TestClient, tenant: str) -> list[str]:
    """Every GET route, from the OpenAPI schema: ``app.routes`` hides included routers
    (RAID, readiness, retro) behind a wrapper, which an earlier draft of this test missed."""
    out = []
    for path, ops in client.app.openapi()["paths"].items():  # type: ignore[attr-defined]
        if "get" not in ops or path in SKIP:
            continue
        for k, v in {**PATH_VALUES[tenant], "item_id": "1", "update_id": "1",
                     "scenario_id": "1"}.items():  # fmt: skip
            path = path.replace("{" + k + "}", v)
        out.append(path)
    return sorted(set(out))


@pytest.mark.parametrize(
    ("tenant", "own", "foreign"),
    [("demo", DEMO_MARKERS, ACME_MARKERS), ("acme", ACME_MARKERS, DEMO_MARKERS)],
)
def test_no_get_endpoint_shows_another_tenants_data(
    client: TestClient, tenant: str, own: tuple[str, ...], foreign: tuple[str, ...]
) -> None:
    leaks, errors, showing_own = [], [], []
    paths = _paths(client, tenant)
    for path in paths:
        res = client.get(path, headers=_as(tenant, path))
        if res.status_code >= 500:
            errors.append((path, res.status_code))
        leaks += [(path, m) for m in foreign if m in res.text]
        if res.status_code == 200 and any(m in res.text for m in own):
            showing_own.append(path)
    assert leaks == []
    assert errors == []
    # The check is only meaningful if the tenant's own data does come back.
    assert {"/raid/summary", "/readiness", "/retro", "/retro/patterns"} <= set(paths)
    assert len(paths) >= 30
    name = PATH_VALUES[tenant]["name"]
    assert {f"/releases/{name}/features", f"/releases/{name}/summary"} <= set(showing_own)


def test_each_tenant_sees_its_own_release(client: TestClient) -> None:
    demo = client.get("/releases").json()
    acme = client.get("/releases", headers=_as("acme", "/releases")).json()
    names = lambda body: {r["name"] for r in body}  # noqa: E731
    assert "v1.38" in names(demo)
    assert "v9.99" not in names(demo)
    assert names(acme) == {"v9.99"}


def test_another_tenants_release_is_not_found(client: TestClient) -> None:
    path = "/releases/v1.38/summary"
    assert client.get(path, headers=_as("acme", path)).status_code == 404
