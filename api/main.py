"""FastAPI service: release health, feature detail, unlinked load, live updates (SSE)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from starlette.concurrency import run_in_threadpool

from api.live import Updates
from api.schemas import FeatureDetailOut, FeaturesOut, LoadOut, ReleaseOut
from api.service import ReleaseService, ReleaseView
from api.views import feature_detail, feature_row, release_out

SERVICE_NAME = "tpm-api"
ENHANCEMENTS_REPO = "kubernetes/enhancements"

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def create_app(
    service: ReleaseService | None = None,
    updates: Updates | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Build the API. ``service`` defaults to Postgres-backed; ``updates`` to Redis."""
    app = FastAPI(title="TPM Intelligence API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:3000"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    state: dict[str, Any] = {"service": service, "updates": updates}

    def svc() -> ReleaseService:
        if state["service"] is None:
            state["service"] = _default_service()
        result: ReleaseService = state["service"]
        return result

    async def view(name: str) -> ReleaseView:
        try:
            return await run_in_threadpool(svc().view, name)
        except KeyError as exc:
            raise HTTPException(404, f"unknown release {name}") from exc

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    @app.get("/releases", response_model=list[ReleaseOut])
    async def releases() -> list[ReleaseOut]:
        """Known releases, oldest first."""
        keys = await run_in_threadpool(svc().release_keys)
        return [release_out(await view(k.split(":", 1)[1])) for k in keys]

    @app.get("/releases/{name}/features", response_model=FeaturesOut)
    async def features(name: str, include_removed: bool = True) -> FeaturesOut:
        """Release health table: odds, flags and linked PRs for every feature."""
        v = await view(name)
        rows = [feature_row(v, a) for a in v.assessment.features if include_removed or a.in_release]
        return FeaturesOut(
            release=release_out(v),
            features=rows,
            calibration=v.calibration.describe(),
            validation=v.validation.as_dict(),
        )

    @app.get("/releases/{name}/features/{number}", response_model=FeatureDetailOut)
    async def feature(name: str, number: int) -> FeatureDetailOut:
        """Feature page: PRs, critical path, timeline, odds and the inputs behind them."""
        v = await view(name)
        a = v.feature(f"{ENHANCEMENTS_REPO}#{number}")
        if a is None:
            raise HTTPException(404, f"feature #{number} was never in {name}")
        return feature_detail(v, a)

    @app.get("/releases/{name}/load", response_model=LoadOut)
    async def load(name: str) -> LoadOut:
        """Open PRs not linked to any feature, per SIG. Not per person (CLAUDE.md section 10)."""
        v = await view(name)
        return LoadOut(
            release=v.assessment.release.key,
            as_of=v.assessment.as_of,
            by_sig=[
                {"sig": s, "open_unlinked_prs": n} for s, n in v.assessment.unlinked_open_prs_by_sig
            ],
        )

    @app.get("/releases/{name}/stream")
    async def stream(name: str, request: Request) -> StreamingResponse:
        """Server-Sent Events: an ``update`` event whenever new data changes the release."""
        await view(name)  # 404 early for unknown releases
        hub = state["updates"] or _default_updates()
        state["updates"] = hub

        async def events() -> AsyncIterator[str]:
            yield _sse("ready", {"release": name, "version": svc().version})
            async for ctx in hub.subscribe(request.is_disconnected):
                if ctx is None:
                    yield ": heartbeat\n\n"
                    continue
                # Continue the trace started by the collector (via queue and worker).
                with tracer.start_as_current_span(
                    "api.push_update", context=ctx, attributes={"tpm.release": name}
                ):
                    before = svc().version
                    await run_in_threadpool(svc().refresh)
                    if svc().version == before:
                        continue
                    v = await view(name)
                    yield _sse(
                        "update",
                        {
                            "release": name,
                            "version": v.version,
                            "as_of": v.assessment.as_of.isoformat(),
                        },
                    )

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz")
    return app


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _default_service() -> ReleaseService:
    from sqlalchemy.orm import sessionmaker

    from api.service import PostgresEventSource
    from pipeline.store.session import make_engine

    return ReleaseService(PostgresEventSource(sessionmaker(make_engine())))


def _default_updates() -> Updates:
    import os

    from api.live import RedisUpdates

    return RedisUpdates(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def main() -> None:
    """Run under uvicorn with telemetry initialised first."""
    import os

    import uvicorn

    from observability.telemetry import init_telemetry

    telemetry = init_telemetry(SERVICE_NAME)
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    try:
        uvicorn.run(
            create_app(cors_origins=origins),
            host="0.0.0.0",  # noqa: S104
            port=int(os.getenv("PORT", "8000")),
            log_config=None,
        )
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    main()
