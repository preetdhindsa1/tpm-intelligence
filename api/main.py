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

from api.ai import AIServices
from api.live import Updates
from api.schemas import (
    ClaimOutApi,
    DecisionIn,
    ExecUpdateOut,
    FeatureDetailOut,
    FeaturesOut,
    LoadOut,
    ReleaseOut,
    RiskNoteOut,
    UpdateEditIn,
    UpdateWarningOut,
)
from api.service import ReleaseService, ReleaseView
from api.views import feature_detail, feature_row, release_out, release_summary_out

SERVICE_NAME = "tpm-api"
ENHANCEMENTS_REPO = "kubernetes/enhancements"

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def create_app(
    service: ReleaseService | None = None,
    updates: Updates | None = None,
    cors_origins: list[str] | None = None,
    ai: AIServices | None = None,
) -> FastAPI:
    """Build the API. ``service`` defaults to Postgres-backed; ``updates`` to Redis."""
    app = FastAPI(title="TPM Intelligence API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:3000"],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )
    state: dict[str, Any] = {"service": service, "updates": updates}
    ai_services = ai or AIServices()

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
        """Known releases, oldest first. Dates and counts only: no forecast is run."""
        return [release_summary_out(r) for r in await run_in_threadpool(svc().releases)]

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

    @app.get("/releases/{name}/features/{number}/risk-note", response_model=RiskNoteOut)
    async def feature_risk_note(name: str, number: int) -> RiskNoteOut:
        """Why this feature is at risk, in verified claims. May call Claude (on demand only)."""
        v = await view(name)
        a = v.feature(f"{ENHANCEMENTS_REPO}#{number}")
        if a is None:
            raise HTTPException(404, f"feature #{number} was never in {name}")
        result = await run_in_threadpool(ai_services.risk_note, v, a)
        note = result.note
        if note is None:
            return RiskNoteOut(status=result.status.value, reason=result.reason)
        removed = {k.removeprefix("removed."): n for k, n in note.counts.items() if k != "verified"}
        validated = note.facts.get(f"feature:{a.key}::odds.validated")
        return RiskNoteOut(
            status=result.status.value,
            reason=result.reason,
            claims=[
                ClaimOutApi(text=c.text, type=c.type.value, refs=list(c.refs), value=c.value)
                for c in note.claims
            ],
            claims_removed=sum(removed.values()),
            removed_by_reason={k: n for k, n in removed.items() if n},
            attempts=note.attempts,
            model=note.model,
            prompt_version=note.prompt_version,
            generated_at=note.created_at,
            cost_usd=round(note.cost_usd, 6),
            odds_validated=validated.value if validated is not None else None,  # type: ignore[arg-type]
        )

    # ---------------------------------------------------------------- executive updates

    def update_out(update: Any, stale: bool) -> ExecUpdateOut:
        from agents.vp_summary import to_markdown

        return ExecUpdateOut(
            id=update.id,
            release=update.release_key,
            status=update.status.value,
            stale=stale,
            header=update.header,
            sections={
                name: [
                    ClaimOutApi(text=c.text, type=c.type.value, refs=list(c.refs), value=c.value)
                    for c in claims
                ]
                for name, claims in update.sections.items()
            },
            word_count=update.word_count(),
            claims_removed=len(update.removed),
            removed=update.removed,
            trimmed_for_length=update.trimmed_for_length,
            attempts=update.attempts,
            model=update.model,
            prompt_version=update.prompt_version,
            cost_usd=round(update.cost_usd, 6),
            edited=update.edited,
            warnings=[UpdateWarningOut(**w.__dict__) for w in update.warnings],
            decided_by=update.decided_by,
            decided_at=update.decided_at,
            decision_note=update.decision_note,
            approved_with_warnings=update.approved_with_warnings,
            approved_while_stale=update.approved_while_stale,
            created_at=update.created_at,
            markdown=to_markdown(update),
        )

    async def owned_update(name: str, update_id: int) -> tuple[ReleaseView, Any]:
        v = await view(name)
        update = await run_in_threadpool(ai_services.get_update, update_id)
        if update is None or update.release_key != v.assessment.release.key:
            raise HTTPException(404, f"update {update_id} not found for {name}")
        return v, update

    @app.post("/releases/{name}/updates", response_model=ExecUpdateOut, status_code=201)
    async def create_update(name: str) -> ExecUpdateOut:
        """Draft an executive update (calls Claude; essential). Never sent anywhere."""
        from agents.gateway import AIError, BudgetExceededError

        v = await view(name)
        try:
            update = await run_in_threadpool(ai_services.draft, v)
        except BudgetExceededError as exc:
            raise HTTPException(429, f"AI budget: {exc.decision.reason}") from exc
        except AIError as exc:
            raise HTTPException(502, str(exc)) from exc
        return update_out(update, stale=False)

    @app.get("/releases/{name}/updates", response_model=list[ExecUpdateOut])
    async def list_updates(name: str) -> list[ExecUpdateOut]:
        """Drafts and decisions for a release, newest first."""
        v = await view(name)
        rows = await run_in_threadpool(ai_services.list_updates, v)
        return [update_out(u, stale) for u, stale in rows]

    @app.get("/releases/{name}/updates/{update_id}", response_model=ExecUpdateOut)
    async def get_update(name: str, update_id: int) -> ExecUpdateOut:
        """One update, with Markdown for copying out."""
        v, update = await owned_update(name, update_id)
        return update_out(update, await run_in_threadpool(ai_services.stale, v, update))

    @app.patch("/releases/{name}/updates/{update_id}", response_model=ExecUpdateOut)
    async def edit_update(name: str, update_id: int, body: UpdateEditIn) -> ExecUpdateOut:
        """Remove or reword claims in a draft; each claim is re-checked."""
        from agents.vp_summary import UpdateError
        from verify.claims import Claim

        v, _ = await owned_update(name, update_id)
        try:
            sections = {
                section: [Claim.model_validate(c.model_dump()) for c in claims]
                for section, claims in body.sections.items()
            }
            update = await run_in_threadpool(ai_services.edit, update_id, sections)
        except UpdateError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return update_out(update, await run_in_threadpool(ai_services.stale, v, update))

    async def _decide(name: str, update_id: int, body: DecisionIn, approve: bool) -> ExecUpdateOut:
        from agents.vp_summary import UpdateError

        v, _ = await owned_update(name, update_id)
        try:
            update = await run_in_threadpool(
                lambda: ai_services.decide(
                    v,
                    update_id,
                    approve=approve,
                    acknowledge_warnings=body.acknowledge_warnings,
                    acknowledge_stale=body.acknowledge_stale,
                    note=body.note,
                )
            )
        except UpdateError as exc:
            raise HTTPException(409, str(exc)) from exc
        return update_out(update, stale=False)

    @app.post("/releases/{name}/updates/{update_id}/approve", response_model=ExecUpdateOut)
    async def approve_update(name: str, update_id: int, body: DecisionIn) -> ExecUpdateOut:
        """TPM approval. Records who and when; the platform still sends nothing."""
        return await _decide(name, update_id, body, approve=True)

    @app.post("/releases/{name}/updates/{update_id}/reject", response_model=ExecUpdateOut)
    async def reject_update(name: str, update_id: int, body: DecisionIn) -> ExecUpdateOut:
        """TPM rejection, with an optional note."""
        return await _decide(name, update_id, body, approve=False)

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
