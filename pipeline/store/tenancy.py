"""Which tenant a database session works for (ADR-0034, #231).

Every transaction runs ``set_config('app.tenant_id', <tenant>, true)`` first, so the
database knows the tenant: new rows take it as their ``tenant_id`` default (migration 0014)
and row-level security (#232) shows only its rows. A transaction with no tenant sets
nothing, so its writes fail and, under RLS, its reads return nothing: fail closed.

The tenant comes from, in order:

1. ``session.info["tenant_id"]``, set by :func:`tenant_sessions` for code that holds a
   factory for one tenant;
2. :data:`current_tenant`, a context variable set per request by the API middleware and by
   each job's entry point with :func:`use_tenant`.

Context variables follow ``asyncio`` tasks and ``run_in_threadpool``, but not a plain
``threading.Thread``. Code that starts a thread passes the tenant on with
:func:`in_tenant`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.orm import Session, sessionmaker

DEMO = "demo"  # the public demo tenant: Kubernetes, Kafka and this repository
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)


def valid(tenant: str) -> str:
    """The tenant id, or ValueError if it is not a slug (it reaches SQL as a bound value,
    but a bad id should fail here, early and clearly)."""
    if not SLUG.match(tenant):
        raise ValueError(f"not a tenant id: {tenant!r}")
    return tenant


@contextmanager
def use_tenant(tenant: str) -> Iterator[str]:
    """Run the block for ``tenant``: every session opened inside it is scoped to it."""
    token = current_tenant.set(valid(tenant))
    try:
        yield tenant
    finally:
        current_tenant.reset(token)


def cli_tenant() -> str:
    """The tenant a command-line job runs for: ``TPM_TENANT``, else the public demo."""
    import os

    return valid(os.getenv("TPM_TENANT", DEMO).strip() or DEMO)


def in_tenant[T](tenant: str, fn: Callable[..., T]) -> Callable[..., T]:
    """``fn`` wrapped to run for ``tenant``: for thread targets, which lose the context."""
    valid(tenant)

    def run(*args: Any, **kwargs: Any) -> T:
        with use_tenant(tenant):
            return fn(*args, **kwargs)

    return run


def carry[T](fn: Callable[..., T]) -> Callable[..., T]:
    """``fn`` wrapped to run for the caller's current tenant in another thread (a thread
    pool, say). With no current tenant it stays without one: fail closed."""
    tenant = current_tenant.get()
    return fn if tenant is None else in_tenant(tenant, fn)


def tenant_sessions(factory: sessionmaker[Session], tenant: str) -> sessionmaker[Session]:
    """A session factory whose sessions always work for ``tenant``, whatever the context."""
    info = {**(factory.kw.get("info") or {}), "tenant_id": valid(tenant)}
    return sessionmaker(class_=factory.class_, **{**factory.kw, "info": info})


def tenant_of(session: Session) -> str | None:
    """The tenant this session's transactions use, or None."""
    explicit = session.info.get("tenant_id")
    return explicit if explicit is not None else current_tenant.get()


@event.listens_for(Session, "after_begin")
def _scope_transaction(session: Session, transaction: Any, connection: Any) -> None:
    tenant = tenant_of(session)
    if tenant is not None:
        connection.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": valid(tenant)}
        )
