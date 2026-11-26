"""Which tenant a request is for, and the caller's role in it (ADR-0034, #231).

The web server forwards ``X-TPM-Tenant``. Without it the request is for the public demo,
as every request was before tenants existed. For any other tenant:

- the tenant must exist: unknown is 404; a directory that cannot be read is 503, never a
  fallback to the demo;
- reading it needs a signed-in member: 401 when not signed in, 404 when signed in but not
  a member (a non-member learns nothing, not even that it exists);
- the signature must be version 2, which covers the tenant (``api.auth``).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import HTTPException, Request

from pipeline.store.tenancy import DEMO, SLUG

logger = logging.getLogger(__name__)
ROLES = ("reader", "approver", "owner")


@dataclass(frozen=True)
class TenantInfo:
    id: str
    name: str
    public: bool


@dataclass(frozen=True)
class Access:
    """The request's tenant and, for a private tenant, the caller's role."""

    tenant: str
    role: str | None = None  # None for the public demo: ADR-0016 rules apply there

    @property
    def approver(self) -> bool:
        return self.role in ("approver", "owner")


DEMO_ACCESS = Access(DEMO)


class TenantDirectory(Protocol):
    def tenant(self, tenant_id: str) -> TenantInfo | None: ...
    def role(self, tenant_id: str, login: str) -> str | None: ...


@dataclass
class MemoryDirectory:
    """Tenants and members in memory: the public demo only, unless tests add more."""

    tenants: dict[str, TenantInfo] = field(
        default_factory=lambda: {DEMO: TenantInfo(DEMO, "Public demo", True)}
    )
    members: Mapping[tuple[str, str], str] = field(default_factory=dict)

    def tenant(self, tenant_id: str) -> TenantInfo | None:
        return self.tenants.get(tenant_id)

    def role(self, tenant_id: str, login: str) -> str | None:
        return self.members.get((tenant_id, login.lower()))


class PostgresDirectory:
    """``tenants`` and ``members`` (migration 0013)."""

    def __init__(self, sessions: object) -> None:
        self._sessions = sessions  # sessionmaker; typed loosely to keep imports lazy

    def tenant(self, tenant_id: str) -> TenantInfo | None:
        from sqlalchemy import select

        from pipeline.store.models import Tenant

        with self._sessions() as s:  # type: ignore[operator]
            row = s.scalars(select(Tenant).where(Tenant.id == tenant_id)).first()
            return TenantInfo(row.id, row.name, row.public) if row else None

    def role(self, tenant_id: str, login: str) -> str | None:
        from sqlalchemy import select

        from pipeline.store.models import Member
        from pipeline.store.tenancy import use_tenant

        with use_tenant(tenant_id), self._sessions() as s:  # type: ignore[operator]
            role = s.scalar(select(Member.role).where(Member.tenant_id == tenant_id,
                                                      Member.login == login.lower()))  # fmt: skip
            return str(role) if role else None


def requested_tenant(request: Request) -> str:
    """The tenant named by ``X-TPM-Tenant``, or the demo. 404 for a malformed id."""
    raw = (request.headers.get("x-tpm-tenant") or "").strip()
    if not raw or raw == DEMO:
        return DEMO
    if not SLUG.match(raw):
        raise HTTPException(404, "unknown tenant")
    return raw


def check_access(tenant: str, login: str | None, directory: TenantDirectory) -> Access:
    """The caller's access to ``tenant``, given the verified login (None: not signed in)."""
    if tenant == DEMO:
        return DEMO_ACCESS
    try:
        info = directory.tenant(tenant)
    except Exception as exc:  # never fall back to the demo
        logger.exception("tenant directory unavailable")
        raise HTTPException(503, "tenants cannot be read right now") from exc
    if info is None:
        raise HTTPException(404, "unknown tenant")
    if info.public:
        return Access(tenant)
    if login is None:
        raise HTTPException(401, "sign in to see this organization")
    try:
        role = directory.role(tenant, login)
    except Exception as exc:
        logger.exception("tenant directory unavailable")
        raise HTTPException(503, "tenants cannot be read right now") from exc
    if role not in ROLES:
        raise HTTPException(404, "unknown tenant")
    return Access(tenant, role)
