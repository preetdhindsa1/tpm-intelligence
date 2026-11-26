"""Connectors per tenant (ADR-0035, #233): ``/tenants/{id}/connectors``.

The path's tenant must be the request's tenant (``X-TPM-Tenant``, resolved and checked by the
middleware): anything else is 404, so one tenant cannot even probe another. Members read;
owners change. The public demo's connectors are the YAML files in the repository, readable
by anyone and never changed through the API.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from api.tenants import Access
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


def tenant_admin_router(
    acting: Callable[[Request], Awaitable[Any]],
    store: Callable[[str], TeamConfigStore],
) -> APIRouter:
    """``acting`` is the app's who-is-this dependency; ``store(tenant)`` its config store."""
    router = APIRouter(tags=["tenants"])

    def owner(request: Request, tenant_id: str, who: Any) -> str:
        access = _access(request, tenant_id)
        if tenant_id == DEMO:
            raise HTTPException(403, "the public demo's connectors are changed in the repository")
        if not getattr(who, "signed_in", False) or access.role != "owner":
            raise HTTPException(403, "only an owner of this organization can change connectors")
        return tenant_id

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
        owner(request, tenant_id, who)
        if body.get("id") != team_id:
            raise HTTPException(422, f"config id must be {team_id!r}")
        try:
            row = await run_in_threadpool(lambda: store(tenant_id).put(body))
        except ValueError as exc:  # pydantic ValidationError is a ValueError
            raise HTTPException(422, str(exc)) from exc
        clear_team_cache()
        return _out(tenant_id, row)

    @router.delete("/tenants/{tenant_id}/connectors/{team_id}", status_code=204)
    async def delete_connector(
        tenant_id: str, team_id: str, request: Request, who: Any = Depends(acting)
    ) -> None:
        owner(request, tenant_id, who)
        if not await run_in_threadpool(lambda: store(tenant_id).delete(team_id)):
            raise HTTPException(404, f"no connector {team_id!r}")
        clear_team_cache()

    return router
