"""One tenant never sees another's data (ADR-0034, #232), on real Postgres with RLS.

The tests connect as a non-superuser role, as the app does on Cloud SQL: a Postgres
superuser (the local Docker user) bypasses row-level security, so it would prove nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from pipeline.store.models import Base, PullRequest
from pipeline.store.tenancy import current_tenant, use_tenant

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 27, tzinfo=UTC)


def _pr(number: int, **kw: Any) -> PullRequest:
    return PullRequest(repo="kubernetes/kubernetes", number=number, title=f"PR {number}",
                       state="open", created_at=NOW, updated_at=NOW, **kw)  # fmt: skip


@pytest.fixture
def seeded(app_engine: Engine) -> Iterator[sessionmaker[Session]]:
    """PR 1 for the demo, PR 2 for acme, written through the app role."""
    factory = sessionmaker(app_engine)
    for tenant, number in (("demo", 1), ("acme", 2)):
        with use_tenant(tenant), factory() as s, s.begin():
            s.add(_pr(number))
    yield factory
    for tenant in ("demo", "acme"):
        with use_tenant(tenant), factory() as s, s.begin():
            s.execute(text("DELETE FROM pull_requests WHERE number IN (1, 2)"))


def _numbers(factory: sessionmaker[Session]) -> list[int]:
    with factory() as s:
        return list(s.scalars(text("SELECT number FROM pull_requests ORDER BY number")))


def test_every_tenant_table_has_forced_rls_and_a_policy(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   EXISTS (SELECT 1 FROM pg_policies p WHERE p.tablename = c.relname)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'""")
        ).all()
    state = {r[0]: tuple(r[1:]) for r in rows}
    tenant_tables = set(Base.metadata.tables) - {"tenants"}
    missing = sorted(t for t in tenant_tables if state.get(t) != (True, True, True))
    assert missing == [], "every tenant table needs forced RLS and a policy (ADR-0034)"


def test_each_tenant_sees_only_its_rows(seeded: sessionmaker[Session]) -> None:
    with use_tenant("demo"):
        assert _numbers(seeded) == [1]
    with use_tenant("acme"):
        assert _numbers(seeded) == [2]
    with use_tenant("globex"):
        assert _numbers(seeded) == []


def test_no_tenant_reads_nothing_and_writes_nothing(seeded: sessionmaker[Session]) -> None:
    token = current_tenant.set(None)
    try:
        assert _numbers(seeded) == []
        with seeded() as s:
            s.add(_pr(3))
            with pytest.raises(DBAPIError):
                s.flush()
    finally:
        current_tenant.reset(token)


def test_a_tenant_cannot_write_or_move_rows_into_another(seeded: sessionmaker[Session]) -> None:
    with use_tenant("acme"), seeded() as s:
        s.add(_pr(4, tenant_id="demo"))
        with pytest.raises(ProgrammingError, match="row-level security"):
            s.flush()
    with (
        use_tenant("acme"),
        seeded() as s,
        s.begin(),
        pytest.raises(ProgrammingError, match="row-level security"),
    ):
        s.execute(text("UPDATE pull_requests SET tenant_id = 'demo' WHERE number = 2"))
    with use_tenant("acme"), seeded() as s, s.begin():
        # acme cannot touch the demo's row: the update matches nothing.
        done = s.execute(text("UPDATE pull_requests SET title = 'x' WHERE number = 1"))
        assert done.rowcount == 0  # type: ignore[attr-defined]


def test_the_same_key_in_two_tenants_does_not_collide(seeded: sessionmaker[Session]) -> None:
    with use_tenant("acme"), seeded() as s, s.begin():
        s.add(_pr(1))  # the demo already has PR 1
    with use_tenant("acme"):
        assert _numbers(seeded) == [1, 2]
    with use_tenant("acme"), seeded() as s, s.begin():
        s.execute(text("DELETE FROM pull_requests WHERE number = 1"))


def test_team_configs_are_per_tenant(app_engine: Engine) -> None:
    from connectors.store import PostgresTeamConfigStore
    from pipeline.store.tenancy import tenant_sessions
    from tests.api.test_connectors_api import WEB

    factory = sessionmaker(app_engine)
    acme = PostgresTeamConfigStore(tenant_sessions(factory, "acme"))
    globex = PostgresTeamConfigStore(tenant_sessions(factory, "globex"))
    try:
        assert acme.put(WEB).version == 1
        assert acme.put(WEB).version == 2
        assert [r.config.id for r in acme.list()] == ["acme-web"]
        assert globex.list() == []
        assert globex.delete("acme-web") is False  # cannot touch acme's row
    finally:
        acme.delete("acme-web")
