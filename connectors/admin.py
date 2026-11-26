"""Tenant administration (ADR-0034, ADR-0035, #234): tenants, members, limits, audit,
export and deletion. Postgres, under row-level security, with an in-memory twin for tests.

Every change is written to the append-only audit log in the same transaction. Deletion
removes every row the tenant owns, in one transaction, and leaves one entry under the
``system`` tenant so the deletion itself can be shown later.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from pipeline.store.tenancy import DEMO, SLUG, use_tenant

RESERVED = frozenset({DEMO, "system"})
ROLES = ("reader", "approver", "owner")


class AdminError(ValueError):
    """A refused change: ``status`` is the HTTP status the API answers with."""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Membership:
    tenant: str
    name: str
    role: str
    public: bool


@dataclass(frozen=True)
class Limits:
    ai_daily_budget_usd: float
    max_teams: int


@dataclass(frozen=True)
class AuditEntry:
    id: int
    at: datetime
    actor_role: str
    action: str
    target: str
    details: dict[str, Any]


class TenantAdmin(Protocol):
    def memberships(self, login: str) -> list[Membership]: ...
    def create(self, tenant: str, name: str, owner: str) -> Membership: ...
    def members(self, tenant: str) -> list[tuple[str, str, datetime]]: ...
    def set_role(self, tenant: str, login: str, role: str, by: tuple[str, str]) -> None: ...
    def remove(self, tenant: str, login: str, by: tuple[str, str]) -> None: ...
    def limits(self, tenant: str) -> Limits: ...
    def set_limits(self, tenant: str, limits: Limits, by: tuple[str, str]) -> Limits: ...
    def audit(self, tenant: str, before: int | None, limit: int) -> list[AuditEntry]: ...
    def record(self, tenant: str, by: tuple[str, str], action: str, target: str,
               details: dict[str, Any] | None = None) -> None: ...  # fmt: skip
    def export(self, tenant: str) -> Iterator[str]: ...
    def delete(self, tenant: str, by: tuple[str, str]) -> None: ...


def check_new_id(tenant: str) -> str:
    if tenant in RESERVED or not SLUG.match(tenant):
        raise AdminError(f"{tenant!r} cannot be a tenant id", 422)
    return tenant


def check_role(role: str) -> str:
    if role not in ROLES:
        raise AdminError(f"role must be one of {', '.join(ROLES)}", 422)
    return role


# ---------------------------------------------------------------- Postgres


class PostgresTenantAdmin:
    """On Postgres. ``sessions`` is a plain factory: each method scopes its own tenant."""

    def __init__(self, sessions: Any) -> None:
        self._sessions = sessions

    def memberships(self, login: str) -> list[Membership]:
        from sqlalchemy import select, text

        from pipeline.store.models import Tenant

        login = login.lower()
        with self._sessions() as s:
            tenants = s.scalars(select(Tenant).where(~Tenant.id.in_(RESERVED))).all()
        out = []
        for t in tenants:  # members is under RLS: read each tenant's own row
            with use_tenant(t.id), self._sessions() as s:
                role = s.scalar(text("SELECT role FROM members WHERE login = :l"), {"l": login})
            if role:
                out.append(Membership(t.id, t.name, str(role), t.public))
        return out

    def create(self, tenant: str, name: str, owner: str) -> Membership:
        from sqlalchemy.exc import IntegrityError

        from pipeline.store.models import AuditRecord, Member, Tenant

        check_new_id(tenant)
        try:
            with self._sessions() as s, s.begin():
                s.add(Tenant(id=tenant, name=name))
                s.flush()
            with use_tenant(tenant), self._sessions() as s, s.begin():
                s.add(Member(tenant_id=tenant, login=owner.lower(), role="owner"))
                s.add(AuditRecord(actor_login=owner.lower(), actor_role="owner",
                                  action="tenant_created", target=tenant))  # fmt: skip
        except IntegrityError as exc:
            raise AdminError(f"tenant {tenant!r} already exists") from exc
        return Membership(tenant, name, "owner", False)

    def members(self, tenant: str) -> list[tuple[str, str, datetime]]:
        from sqlalchemy import select

        from pipeline.store.models import Member

        with use_tenant(tenant), self._sessions() as s:
            rows = s.scalars(select(Member).where(Member.tenant_id == tenant)
                             .order_by(Member.login)).all()  # fmt: skip
            return [(m.login, m.role, m.added_at) for m in rows]

    def _owners_after(self, s: Any, tenant: str, login: str, role: str | None) -> int:
        """How many owners the tenant would have after ``login`` gets ``role`` (None: removed)."""
        from sqlalchemy import select

        from pipeline.store.models import Member

        owners = set(s.scalars(select(Member.login).where(Member.tenant_id == tenant,
                                                          Member.role == "owner")))  # fmt: skip
        owners.discard(login)
        return len(owners) + (1 if role == "owner" else 0)

    def set_role(self, tenant: str, login: str, role: str, by: tuple[str, str]) -> None:
        from pipeline.store.models import AuditRecord, Member

        check_role(role)
        login = login.lower()
        with use_tenant(tenant), self._sessions() as s, s.begin():
            if self._owners_after(s, tenant, login, role) == 0:
                raise AdminError("an organization keeps at least one owner")
            s.merge(Member(tenant_id=tenant, login=login, role=role))
            s.add(AuditRecord(actor_login=by[0], actor_role=by[1], action="member_role_set",
                              target=login, details={"role": role}))  # fmt: skip

    def remove(self, tenant: str, login: str, by: tuple[str, str]) -> None:
        from sqlalchemy import delete

        from pipeline.store.models import AuditRecord, Member

        login = login.lower()
        with use_tenant(tenant), self._sessions() as s, s.begin():
            if self._owners_after(s, tenant, login, None) == 0:
                raise AdminError("an organization keeps at least one owner")
            done = s.execute(delete(Member).where(Member.tenant_id == tenant,
                                                  Member.login == login))  # fmt: skip
            if not done.rowcount:
                raise AdminError(f"{login} is not a member", 404)
            s.add(AuditRecord(actor_login=by[0], actor_role=by[1], action="member_removed",
                              target=login))  # fmt: skip

    def limits(self, tenant: str) -> Limits:
        from pipeline.store.models import Tenant

        with self._sessions() as s:
            t = s.get(Tenant, tenant)
            if t is None:
                raise AdminError("unknown tenant", 404)
            return Limits(float(t.ai_daily_budget_usd), t.max_teams)

    def set_limits(self, tenant: str, limits: Limits, by: tuple[str, str]) -> Limits:
        from pipeline.store.models import AuditRecord, Tenant

        if not 0 <= limits.ai_daily_budget_usd <= 50 or not 1 <= limits.max_teams <= 50:
            raise AdminError("AI budget must be $0-50 a day and teams 1-50", 422)
        with self._sessions() as s, s.begin():
            t = s.get(Tenant, tenant)
            if t is None:
                raise AdminError("unknown tenant", 404)
            old = Limits(float(t.ai_daily_budget_usd), t.max_teams)
            t.ai_daily_budget_usd = Decimal(str(limits.ai_daily_budget_usd))
            t.max_teams = limits.max_teams
        with use_tenant(tenant), self._sessions() as s, s.begin():
            s.add(AuditRecord(actor_login=by[0], actor_role=by[1], action="limits_changed",
                              target=tenant, details={"from": old.__dict__,
                                                      "to": limits.__dict__}))  # fmt: skip
        return limits

    def audit(self, tenant: str, before: int | None, limit: int) -> list[AuditEntry]:
        from sqlalchemy import select

        from pipeline.store.models import AuditRecord as A

        with use_tenant(tenant), self._sessions() as s:
            q = select(A).where(A.tenant_id == tenant)
            if before is not None:
                q = q.where(A.id < before)
            rows = s.scalars(q.order_by(A.id.desc()).limit(limit)).all()
            return [AuditEntry(r.id, r.at, r.actor_role, r.action, r.target, r.details)
                    for r in rows]  # fmt: skip

    def record(self, tenant: str, by: tuple[str, str], action: str, target: str,
               details: dict[str, Any] | None = None) -> None:  # fmt: skip
        from pipeline.store.models import AuditRecord

        with use_tenant(tenant), self._sessions() as s, s.begin():
            s.add(AuditRecord(actor_login=by[0], actor_role=by[1], action=action, target=target,
                              details=details or {}))  # fmt: skip

    def export(self, tenant: str) -> Iterator[str]:
        """One JSON line per row the tenant owns, table by table (parents first)."""
        from sqlalchemy import select

        from pipeline.store.models import Base

        with use_tenant(tenant), self._sessions() as s:
            for table in Base.metadata.sorted_tables:
                if table.name == "tenants" or "tenant_id" not in table.c:
                    continue
                for row in s.execute(select(table).where(table.c.tenant_id == tenant)):
                    yield json.dumps({"table": table.name, "row": dict(row._mapping)},
                                     default=str) + "\n"  # fmt: skip

    def delete(self, tenant: str, by: tuple[str, str]) -> None:
        """Every row the tenant owns, children first, then the tenant, in one transaction."""
        from sqlalchemy import delete, text

        from pipeline.store.models import AuditRecord, Base, Tenant

        if tenant in RESERVED:
            raise AdminError("the public demo and the system tenant cannot be deleted", 403)
        counts: dict[str, int] = {}
        with use_tenant(tenant), self._sessions() as s, s.begin():
            # The append-only triggers allow DELETE only in this transaction (migration 0017).
            s.execute(text("SELECT set_config('app.deleting_tenant', :t, true)"), {"t": tenant})
            for table in reversed(Base.metadata.sorted_tables):
                if table.name == "tenants" or "tenant_id" not in table.c:
                    continue
                # An explicit WHERE as well as RLS: a superuser session bypasses RLS.
                done = s.execute(delete(table).where(table.c.tenant_id == tenant))
                counts[table.name] = int(done.rowcount or 0)
            s.execute(delete(Tenant).where(Tenant.id == tenant))
        with use_tenant("system"), self._sessions() as s, s.begin():
            s.add(AuditRecord(actor_login=by[0], actor_role=by[1], action="tenant_deleted",
                              target=tenant,
                              details={"rows": sum(counts.values())}))  # fmt: skip


# ---------------------------------------------------------------- memory (tests)


@dataclass
class MemoryTenantAdmin:
    tenants: dict[str, tuple[str, bool, Limits]] = field(default_factory=dict)
    roles: dict[tuple[str, str], tuple[str, datetime]] = field(default_factory=dict)
    log: list[tuple[str, AuditEntry]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _record(self, tenant: str, by: tuple[str, str], action: str, target: str,
                details: dict[str, Any] | None = None) -> None:  # fmt: skip
        entry = AuditEntry(len(self.log) + 1, datetime.now(UTC), by[1], action, target,
                           details or {})  # fmt: skip
        self.log.append((tenant, entry))

    def memberships(self, login: str) -> list[Membership]:
        return [Membership(t, self.tenants[t][0], role, self.tenants[t][1])
                for (t, who), (role, _) in sorted(self.roles.items())
                if who == login.lower() and t in self.tenants]  # fmt: skip

    def create(self, tenant: str, name: str, owner: str) -> Membership:
        check_new_id(tenant)
        with self._lock:
            if tenant in self.tenants:
                raise AdminError(f"tenant {tenant!r} already exists")
            self.tenants[tenant] = (name, False, Limits(0.5, 3))
            self.roles[(tenant, owner.lower())] = ("owner", datetime.now(UTC))
            self._record(tenant, (owner.lower(), "owner"), "tenant_created", tenant)
        return Membership(tenant, name, "owner", False)

    def members(self, tenant: str) -> list[tuple[str, str, datetime]]:
        return [(who, role, at) for (t, who), (role, at) in sorted(self.roles.items())
                if t == tenant]  # fmt: skip

    def _owners_after(self, tenant: str, login: str, role: str | None) -> int:
        owners = {w for (t, w), (r, _) in self.roles.items() if t == tenant and r == "owner"}
        owners.discard(login)
        return len(owners) + (1 if role == "owner" else 0)

    def set_role(self, tenant: str, login: str, role: str, by: tuple[str, str]) -> None:
        check_role(role)
        with self._lock:
            if self._owners_after(tenant, login.lower(), role) == 0:
                raise AdminError("an organization keeps at least one owner")
            self.roles[(tenant, login.lower())] = (role, datetime.now(UTC))
            self._record(tenant, by, "member_role_set", login.lower(), {"role": role})

    def remove(self, tenant: str, login: str, by: tuple[str, str]) -> None:
        with self._lock:
            if (tenant, login.lower()) not in self.roles:
                raise AdminError(f"{login} is not a member", 404)
            if self._owners_after(tenant, login.lower(), None) == 0:
                raise AdminError("an organization keeps at least one owner")
            del self.roles[(tenant, login.lower())]
            self._record(tenant, by, "member_removed", login.lower())

    def limits(self, tenant: str) -> Limits:
        if tenant not in self.tenants:
            raise AdminError("unknown tenant", 404)
        return self.tenants[tenant][2]

    def set_limits(self, tenant: str, limits: Limits, by: tuple[str, str]) -> Limits:
        if not 0 <= limits.ai_daily_budget_usd <= 50 or not 1 <= limits.max_teams <= 50:
            raise AdminError("AI budget must be $0-50 a day and teams 1-50", 422)
        name, public, old = self.tenants[tenant]
        self.tenants[tenant] = (name, public, limits)
        self._record(tenant, by, "limits_changed", tenant,
                     {"from": old.__dict__, "to": limits.__dict__})  # fmt: skip
        return limits

    def audit(self, tenant: str, before: int | None, limit: int) -> list[AuditEntry]:
        rows = [e for t, e in reversed(self.log) if t == tenant
                and (before is None or e.id < before)]  # fmt: skip
        return rows[:limit]

    def record(self, tenant: str, by: tuple[str, str], action: str, target: str,
               details: dict[str, Any] | None = None) -> None:  # fmt: skip
        self._record(tenant, by, action, target, details)

    def export(self, tenant: str) -> Iterator[str]:
        for (t, who), (role, at) in sorted(self.roles.items()):
            if t == tenant:
                row = {"tenant_id": t, "login": who, "role": role, "added_at": at}
                yield json.dumps({"table": "members", "row": row}, default=str) + "\n"

    def delete(self, tenant: str, by: tuple[str, str]) -> None:
        if tenant in RESERVED:
            raise AdminError("the public demo and the system tenant cannot be deleted", 403)
        with self._lock:
            self.tenants.pop(tenant, None)
            for key in [k for k in self.roles if k[0] == tenant]:
                del self.roles[key]
            self.log = [(t, e) for t, e in self.log if t != tenant]
            self._record("system", by, "tenant_deleted", tenant)
