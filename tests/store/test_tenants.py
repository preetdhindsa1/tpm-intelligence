"""Tenants and tenant_id on every row (ADR-0034, #230), on real Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pipeline.store.models import Base, Member, PullRequest, Tenant

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 27, tzinfo=UTC)


def _pr(tenant: str | None = None) -> PullRequest:
    pr = PullRequest(repo="kubernetes/kubernetes", number=143709, title="t", state="open",
                     created_at=NOW, updated_at=NOW)  # fmt: skip
    if tenant is not None:
        pr.tenant_id = tenant
    return pr


def test_every_table_has_a_tenant_column(session: Session) -> None:
    tables = set(inspect(session.connection()).get_table_names()) - {"alembic_version", "tenants"}
    assert tables == set(Base.metadata.tables) - {"tenants"}
    missing = [
        t for t in sorted(tables)
        if "tenant_id" not in {c["name"] for c in inspect(session.connection()).get_columns(t)}
    ]  # fmt: skip
    assert missing == []


def test_existing_and_default_rows_are_the_public_demo(session: Session) -> None:
    demo = session.get(Tenant, "demo")
    assert demo is not None
    assert demo.public is True
    session.add(_pr())
    session.flush()
    assert session.scalar(select(PullRequest.tenant_id)) == "demo"


def test_two_tenants_may_hold_the_same_pull_request(session: Session) -> None:
    session.add(Tenant(id="acme", name="Acme"))
    session.flush()
    session.add_all([_pr("demo"), _pr("acme")])
    session.flush()
    assert session.scalar(text("SELECT count(*) FROM pull_requests WHERE number = 143709")) == 2


def test_one_tenant_cannot_hold_it_twice(session: Session) -> None:
    session.add_all([_pr("demo"), _pr("demo")])
    with pytest.raises(IntegrityError):
        session.flush()


def test_a_row_for_an_unknown_tenant_is_refused(session: Session) -> None:
    session.add(_pr("nobody"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_member_roles_are_checked(session: Session) -> None:
    session.add(Tenant(id="acme", name="Acme"))
    session.flush()
    session.add(Member(tenant_id="acme", login="octocat", role="owner"))
    session.flush()
    session.add(Member(tenant_id="acme", login="hubot", role="admin"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_tenant_ids_are_slugs(session: Session) -> None:
    session.add(Tenant(id="Acme Corp", name="Acme"))
    with pytest.raises(IntegrityError):
        session.flush()
