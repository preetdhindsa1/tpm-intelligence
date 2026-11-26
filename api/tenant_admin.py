"""Tenant administration (ADR-0034, ADR-0035): connectors (#233); tenants, members,
limits, audit, export and deletion (#234). Contract: docs/api/tenants-contract.md.

The path's tenant must be the request's tenant (``X-TPM-Tenant``, resolved and checked by the
middleware): anything else is 404, so one tenant cannot even probe another. Members read;
owners change. The public demo's connectors are the YAML files in the repository, readable
by anyone and never changed through the API.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.tenants import Access
from connectors.admin import AdminError, Limits, TenantAdmin
from connectors.load import clear_team_cache, load_teams
from connectors.schema import TeamConfig
from connectors.secrets import resolve, secret_name
from connectors.store import StoredTeam, TeamConfigStore
from pipeline.store.tenancy import DEMO


def _access(request: Request, tenant_id: str) -> Access:
    access: Access | None = getattr(request.state, "access", None)
    if access is None or access.tenant != tenant_id:
        raise HTTPException(404, "unknown tenant")
    return access


def _secrets(tenant: str, config: TeamConfig) -> list[dict[str, Any]]:
    if tenant == DEMO:
        return []
    return [
        {"ref": ref, "name": secret_name(tenant, ref), "found": resolve(tenant, ref) is not None}
        for ref in config.secret_refs.values()
    ]


def _out(tenant: str, row: StoredTeam) -> dict[str, Any]:
    return {"team_id": row.config.id, "version": row.version, "updated_at": row.updated_at,
            "config": row.config.model_dump(mode="json"),
            "secrets": _secrets(tenant, row.config)}  # fmt: skip


class TenantIn(BaseModel):
    id: str = Field(min_length=3, max_length=32)
    name: str = Field(min_length=1, max_length=200)


class RoleIn(BaseModel):
    role: str


class LimitsIn(BaseModel):
    ai_daily_budget_usd: float
    max_teams: int


class ConfirmIn(BaseModel):
    confirm: str


def can_create(login: str) -> bool:
    """Tenant creation starts closed: logins in ``TENANT_CREATORS`` (owner decision)."""
    allowed = {x.strip().lower() for x in os.getenv("TENANT_CREATORS", "").split(",") if x.strip()}
    return login.lower() in allowed


def _admin_error(exc: AdminError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def tenant_admin_router(
    acting: Callable[[Request], Awaitable[Any]],
    store: Callable[[str], TeamConfigStore],
    admin: Callable[[], TenantAdmin],
) -> APIRouter:
    """``acting``: who is asking. ``store(tenant)``: its team configs. ``admin()``: tenants."""
    router = APIRouter(tags=["tenants"])

    def owner(request: Request, tenant_id: str, who: Any) -> tuple[str, str]:
        """The acting owner as (login, role) for the audit log, or 403."""
        access = _access(request, tenant_id)
        if tenant_id == DEMO:
            raise HTTPException(403, "the public demo is changed in the repository, not here")
        if not getattr(who, "signed_in", False) or access.role != "owner":
            raise HTTPException(403, "only an owner of this organization can do this")
        return (who.login, "owner")

    def signed(who: Any) -> str:
        if not getattr(who, "signed_in", False):
            raise HTTPException(401, "sign in with GitHub to do this")
        return str(who.login)

    @router.get("/me/tenants")
    async def my_tenants(who: Any = Depends(acting)) -> dict[str, Any]:
        """The signed-in user's organizations, plus the public demo."""
        login = signed(who)
        rows = await run_in_threadpool(lambda: admin().memberships(login))
        demo = {"id": DEMO, "name": "Public demo", "role": "approver" if who.approver else "reader",
                "public": True}  # fmt: skip
        return {"tenants": [demo, *({"id": m.tenant, "name": m.name, "role": m.role,
                                     "public": m.public} for m in rows)],
                "can_create": can_create(login)}  # fmt: skip

    @router.post("/tenants", status_code=201)
    async def create_tenant(body: TenantIn, who: Any = Depends(acting)) -> dict[str, Any]:
        """A new organization; the creator is its first owner."""
        login = signed(who)
        if not can_create(login):
            raise HTTPException(403, "creating organizations is not open yet")
        try:
            m = await run_in_threadpool(lambda: admin().create(body.id, body.name, login))
        except AdminError as exc:
            raise _admin_error(exc) from exc
        return {"id": m.tenant, "name": m.name, "role": m.role, "public": m.public}

    @router.get("/tenants/{tenant_id}/members")
    async def members(
        tenant_id: str, request: Request, who: Any = Depends(acting)
    ) -> dict[str, Any]:
        owner(request, tenant_id, who)
        rows = await run_in_threadpool(lambda: admin().members(tenant_id))
        return {"members": [{"login": login, "role": role, "added_at": at}
                            for login, role, at in rows]}  # fmt: skip

    @router.put("/tenants/{tenant_id}/members/{login}")
    async def set_member(tenant_id: str, login: str, body: RoleIn, request: Request,
                         who: Any = Depends(acting)) -> dict[str, Any]:  # fmt: skip
        by = owner(request, tenant_id, who)
        try:
            await run_in_threadpool(lambda: admin().set_role(tenant_id, login, body.role, by))
        except AdminError as exc:
            raise _admin_error(exc) from exc
        return {"login": login.lower(), "role": body.role}

    @router.delete("/tenants/{tenant_id}/members/{login}", status_code=204)
    async def remove_member(tenant_id: str, login: str, request: Request,
                            who: Any = Depends(acting)) -> None:  # fmt: skip
        by = owner(request, tenant_id, who)
        try:
            await run_in_threadpool(lambda: admin().remove(tenant_id, login, by))
        except AdminError as exc:
            raise _admin_error(exc) from exc

    @router.get("/tenants/{tenant_id}/limits")
    async def get_limits(tenant_id: str, request: Request) -> dict[str, Any]:
        _access(request, tenant_id)
        limits = await run_in_threadpool(lambda: admin().limits(tenant_id))
        teams = len(load_teams(tenant_id))
        return {**asdict(limits), "teams": teams}

    @router.put("/tenants/{tenant_id}/limits")
    async def put_limits(tenant_id: str, body: LimitsIn, request: Request,
                         who: Any = Depends(acting)) -> dict[str, Any]:  # fmt: skip
        by = owner(request, tenant_id, who)
        new = Limits(body.ai_daily_budget_usd, body.max_teams)
        try:
            out = await run_in_threadpool(lambda: admin().set_limits(tenant_id, new, by))
        except AdminError as exc:
            raise _admin_error(exc) from exc
        return asdict(out)

    @router.get("/tenants/{tenant_id}/audit")
    async def audit(tenant_id: str, request: Request, before: int | None = None,
                    who: Any = Depends(acting)) -> dict[str, Any]:  # fmt: skip
        """Newest first. ``actor`` is the role at the time, never the login."""
        owner(request, tenant_id, who)
        rows = await run_in_threadpool(lambda: admin().audit(tenant_id, before, 50))
        return {"entries": [{"id": e.id, "at": e.at, "actor": e.actor_role, "action": e.action,
                             "target": e.target, "details": e.details} for e in rows]}  # fmt: skip

    @router.post("/tenants/{tenant_id}/export")
    async def export(tenant_id: str, request: Request,
                     who: Any = Depends(acting)) -> StreamingResponse:  # fmt: skip
        """Every row the tenant owns, one JSON object per line. Produced now, not kept."""
        by = owner(request, tenant_id, who)
        await run_in_threadpool(lambda: admin().record(tenant_id, by, "export_started", tenant_id))
        lines = await run_in_threadpool(lambda: list(admin().export(tenant_id)))
        return StreamingResponse(iter(lines), media_type="application/x-ndjson")

    @router.delete("/tenants/{tenant_id}", status_code=204)
    async def delete_tenant(tenant_id: str, body: ConfirmIn, request: Request,
                            who: Any = Depends(acting)) -> None:  # fmt: skip
        """Delete every row the tenant owns, then the tenant. Needs its id typed back."""
        by = owner(request, tenant_id, who)
        if body.confirm != tenant_id:
            raise HTTPException(422, "type the organization id to confirm")
        try:
            await run_in_threadpool(lambda: admin().delete(tenant_id, by))
        except AdminError as exc:
            raise _admin_error(exc) from exc
        clear_team_cache()

    @router.get("/tenants/{tenant_id}/connectors")
    async def list_connectors(tenant_id: str, request: Request) -> dict[str, Any]:
        """The tenant's team configs and whether each secret reference resolves."""
        _access(request, tenant_id)
        if tenant_id == DEMO:
            from datetime import UTC, datetime

            rows = [StoredTeam(t, 1, datetime.min.replace(tzinfo=UTC))
                    for t in load_teams(DEMO).values()]  # fmt: skip
        else:
            rows = await run_in_threadpool(lambda: store(tenant_id).list())
        return {"connectors": [_out(tenant_id, r) for r in rows]}

    @router.put("/tenants/{tenant_id}/connectors/{team_id}")
    async def put_connector(
        tenant_id: str, team_id: str, body: dict[str, Any], request: Request,
        who: Any = Depends(acting),
    ) -> dict[str, Any]:  # fmt: skip
        """Create or replace one team config (same schema as a YAML file). 422 if invalid."""
        by = owner(request, tenant_id, who)  # before anything else: a reader learns nothing
        if body.get("id") != team_id:
            raise HTTPException(422, f"config id must be {team_id!r}")
        teams = load_teams(tenant_id)
        try:
            cap = admin().limits(tenant_id).max_teams
        except AdminError as exc:
            raise _admin_error(exc) from exc
        if team_id not in teams and len(teams) >= cap:
            raise HTTPException(409, "this organization is at its team limit")
        try:
            row = await run_in_threadpool(lambda: store(tenant_id).put(body))
        except ValueError as exc:  # pydantic ValidationError is a ValueError
            raise HTTPException(422, str(exc)) from exc
        # The audit keeps the config (secret refs are names, never values).
        await run_in_threadpool(
            lambda: admin().record(
                tenant_id,
                by,
                "connector_changed",
                team_id,
                {"version": row.version, "config": row.config.model_dump(mode="json")},
            )
        )
        clear_team_cache()
        return _out(tenant_id, row)

    @router.delete("/tenants/{tenant_id}/connectors/{team_id}", status_code=204)
    async def delete_connector(
        tenant_id: str, team_id: str, request: Request, who: Any = Depends(acting)
    ) -> None:
        by = owner(request, tenant_id, who)
        if not await run_in_threadpool(lambda: store(tenant_id).delete(team_id)):
            raise HTTPException(404, f"no connector {team_id!r}")
        await run_in_threadpool(lambda: admin().record(tenant_id, by, "connector_deleted", team_id))
        clear_team_cache()

    return router
