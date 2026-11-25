"""FastAPI service: release health, feature detail, unlinked load, live updates (SSE)."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from starlette.concurrency import run_in_threadpool

from api.ai import AIServices
from api.auth import Actor, AuthConfig, identify, require_approver
from api.live import DEBOUNCE_S, Updates, push_timing
from api.schemas import (
    ClaimOutApi,
    DecisionIn,
    DependenciesOut,
    ExecUpdateOut,
    FeatureDetailOut,
    FeaturesOut,
    GraphOut,
    LabOut,
    LinkDecisionIn,
    LinkSuggestionOut,
    LinkSuggestionsOut,
    LoadOut,
    MeOut,
    MergeDatesOut,
    PortfolioOut,
    ReleaseOut,
    RiskNoteOut,
    SavedScenarioOut,
    ScenarioIn,
    SimPoolOut,
    SimulationOut,
    SimulatorOut,
    SnapshotRunOut,
    SnapshotsOut,
    SummaryOut,
    UpdateEditIn,
    UpdateWarningOut,
)
from api.service import ReleaseService, ReleaseView
from api.views import (
    dependencies_out,
    feature_detail,
    feature_row,
    graph_out,
    lab_out,
    lane_specs,
    merge_dates_out,
    program_facts,
    release_out,
    release_summary_out,
    summary_out,
)
from connectors.load import load_teams
from connectors.schema import TeamConfig
from engine.assess import FeatureAssessment
from engine.forecast import DEFAULT_FORECAST, model_version
from engine.lab import lab_report
from engine.portfolio import LabFacts, portfolio

SERVICE_NAME = "tpm-api"
# A live stream ends after this long and the browser reconnects (EventSource does so by
# itself), landing on the newest revision. Without a bound, one open page kept an old
# revision and its worker running for the 60-minute request timeout after a deploy
# (2026-11-23, ADR-0019).
STREAM_MAX_S = 120.0  # 600 s still let an old revision run 5+ min after a deploy (P3-M5)
STREAM_RETRY_MS = 1000
NO_SIMULATOR = (
    "No simulator for {name} yet: it is calibrated on earlier releases of the same project, "
    "and none has been measured."
)
# Security review (docs/security-review.md, #64): one API instance takes 160 concurrent
# requests; open live pages each hold one, so cap them below that and keep room for pages
# and actions. The public simulator is CPU-heavy: at most a couple of runs at once.
MAX_OPEN_STREAMS = 100
MAX_PARALLEL_SIMULATIONS = 2
DEPENDENCIES_CACHE_SIZE = 8  # (release, view version, include_removed) entries (#70)
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
SIM_NOTE = (
    "Decision support, not a guarantee: if these assumptions hold, results are likely in "
    "these ranges."
)
SIM_NOT_VALIDATED = (
    " The simulator is not validated (ADR-0012): do not treat any what-if here as reliable."
)


def sim_note(validated: bool) -> str:
    """Honest wording for every simulator response (CLAUDE.md section 14)."""
    return SIM_NOTE if validated else SIM_NOTE + SIM_NOT_VALIDATED


def feature_by_number(view: ReleaseView, number: int) -> FeatureAssessment | None:
    """The release's feature with this number: ``#6395`` (KEP) or ``KAFKA-20682``."""
    for a in view.assessment.features:
        feature = view.world.features.get(a.key)
        if feature is not None and feature.number == number:
            return a
    return None


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def create_app(
    service: ReleaseService | None = None,
    updates: Updates | None = None,
    cors_origins: list[str] | None = None,
    ai: AIServices | None = None,
    link_store: Any = None,
    sim_store: Any = None,
    snapshot_store: Any = None,
    auth: AuthConfig | None = None,
) -> FastAPI:
    """Build the API. ``service`` defaults to Postgres-backed; ``updates`` to Redis.

    ``auth`` defaults to the environment (``AUTH_MODE``, ``TPM_ACTION_SECRET``,
    ``APPROVERS``; ADR-0016).
    """
    auth_config = auth or AuthConfig.from_env()

    async def acting(request: Request) -> Actor:
        return await identify(request, auth_config)

    async def approver(request: Request) -> Actor:
        return await require_approver(request, auth_config)

    app = FastAPI(title="Program Intelligence Platform API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:3000"],
        allow_methods=["GET", "POST", "PATCH"],
        # Actions come through the web app's server with a signature (ADR-0016), never
        # from the browser directly; CORS covers reads and the live-update stream.
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    simulations = asyncio.Semaphore(MAX_PARALLEL_SIMULATIONS)
    open_streams = {"n": 0}
    state: dict[str, Any] = {
        "service": service,
        "updates": updates,
        "links": link_store,
        "sim_store": sim_store,
        "snapshots": snapshot_store,
        "sim": None,
    }
    ai_services = ai or AIServices()

    def svc() -> ReleaseService:
        if state["service"] is None:
            state["service"] = _default_service()
        result: ReleaseService = state["service"]
        return result

    async def view(name: str, wait: bool = False) -> ReleaseView:
        try:
            return await run_in_threadpool(lambda: svc().view(name, wait=wait))
        except KeyError as exc:
            raise HTTPException(404, f"unknown release {name}") from exc

    def warm_on_boot() -> None:
        """Compute the current release before the first visitor asks, then keep it fresh."""
        s = svc()
        s.start_warmer()
        s.warm(s.current_release_keys())

    app.state.warm_on_boot = warm_on_boot

    @app.get("/me", response_model=MeOut)
    async def me(who: Actor = Depends(acting)) -> MeOut:
        """Who the web app is acting for, and whether they may approve (ADR-0016)."""
        return MeOut(
            login=None if who.login == "anonymous" else who.login,
            signed_in=who.signed_in,
            approver=who.approver,
            mode=auth_config.mode,
        )

    # Cloud Run reserves URL paths ending in "z" for itself (a public /healthz returns 404
    # before reaching the app), so external checks use /health. Container probes still
    # reach /healthz directly.
    @app.get("/health")
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

    @app.get("/lab", response_model=LabOut)
    async def lab(
        project: str = "tpm-intelligence",
        release: str | None = None,
        cap: int = Query(default=2, ge=1, le=20),
        lines: int = Query(default=400, ge=1, le=5000),
    ) -> LabOut:
        """Development-lab counts. This repository uses its whole history.

        Other projects use the selected release's cycle. Teams without agent lanes
        still return opened, merged, and approval counts.
        """
        # The web app sends the URL slug ("kafka"); release keys use "KAFKA".
        wanted = project.lower()
        team = next((t for t in load_teams().values() if t.project.lower() == wanted), None)
        if team is None:
            raise HTTPException(404, f"unknown project {project}")
        project = team.project
        if team.project != "tpm-intelligence" and not release:
            raise HTTPException(404, "release is required")

        def _newest_name() -> str | None:
            rows = [r for r in svc().releases() if r.release.key.split(":", 1)[0] == project]
            return rows[-1].release.name if rows else None

        name = release or await run_in_threadpool(_newest_name)
        if name is None:
            raise HTTPException(404, f"no release for {project}")
        v = await view(name)
        if v.assessment.release.key.split(":", 1)[0] != project:
            raise HTTPException(404, f"unknown project {project}")
        since = _lab_since(team, v)
        report = lab_report(
            v.world,
            v.assessment.release.key,
            lane_specs(team.author_lanes),
            team.reviewer_pool,
            cap_n=cap,
            max_lines=lines,
            since=since,
        )
        return lab_out(report, project=project, lanes_configured=bool(team.author_lanes))

    @app.get("/releases/{name}/features/{number}", response_model=FeatureDetailOut)
    async def feature(name: str, number: int) -> FeatureDetailOut:
        """Feature page: PRs, critical path, timeline, odds and the inputs behind them."""
        v = await view(name)
        a = feature_by_number(v, number)
        if a is None:
            raise HTTPException(404, f"feature #{number} was never in {name}")
        return feature_detail(v, a)

    @app.get("/releases/{name}/features/{number}/risk-note", response_model=RiskNoteOut)
    async def feature_risk_note(
        name: str, number: int, who: Actor = Depends(acting)
    ) -> RiskNoteOut:
        """Why this feature is at risk, in verified claims.

        Anyone sees a stored note. Only an approver can make a new one (paid AI, ADR-0016).
        """
        v = await view(name)
        a = feature_by_number(v, number)
        if a is None:
            raise HTTPException(404, f"feature #{number} was never in {name}")
        result = await run_in_threadpool(lambda: ai_services.risk_note(v, a, generate=who.approver))
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
    async def create_update(name: str, who: Actor = Depends(approver)) -> ExecUpdateOut:
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
    async def edit_update(
        name: str, update_id: int, body: UpdateEditIn, who: Actor = Depends(approver)
    ) -> ExecUpdateOut:
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

    async def _decide(
        name: str, update_id: int, body: DecisionIn, approve: bool, who: Actor
    ) -> ExecUpdateOut:
        from agents.vp_summary import UpdateError

        v, _ = await owned_update(name, update_id)
        try:
            update = await run_in_threadpool(
                lambda: ai_services.decide(
                    v,
                    update_id,
                    approve=approve,
                    approver=who.recorded_as,
                    acknowledge_warnings=body.acknowledge_warnings,
                    acknowledge_stale=body.acknowledge_stale,
                    note=body.note,
                )
            )
        except UpdateError as exc:
            raise HTTPException(409, str(exc)) from exc
        return update_out(update, stale=False)

    @app.post("/releases/{name}/updates/{update_id}/approve", response_model=ExecUpdateOut)
    async def approve_update(
        name: str, update_id: int, body: DecisionIn, who: Actor = Depends(approver)
    ) -> ExecUpdateOut:
        """TPM approval. Records who and when; the platform still sends nothing."""
        return await _decide(name, update_id, body, approve=True, who=who)

    @app.post("/releases/{name}/updates/{update_id}/reject", response_model=ExecUpdateOut)
    async def reject_update(
        name: str, update_id: int, body: DecisionIn, who: Actor = Depends(approver)
    ) -> ExecUpdateOut:
        """TPM rejection, with an optional note."""
        return await _decide(name, update_id, body, approve=False, who=who)

    def links() -> Any:
        if state["links"] is None:
            from sqlalchemy.orm import sessionmaker

            from agents.link_store import PostgresLinkSuggestionStore
            from pipeline.store.session import make_engine

            state["links"] = PostgresLinkSuggestionStore(sessionmaker(make_engine()))
        return state["links"]

    def suggestion_out(v: ReleaseView, row: Any) -> LinkSuggestionOut:
        pr = v.world.pull_requests.get(row.pull_request_key)
        feature = v.world.features.get(row.feature_key)
        return LinkSuggestionOut(
            id=row.id,
            status=row.status.value,
            pull_request=row.pull_request_key,
            pull_request_title=pr.title if pr else None,
            pull_request_url=f"https://github.com/{pr.repo}/pull/{pr.number}" if pr else None,
            pull_request_state=pr.state if pr else None,
            feature=row.feature_key,
            feature_number=feature.number if feature else None,
            feature_title=feature.title if feature else None,
            pr_quote=row.evidence.get("pr_quote", ""),
            feature_quote=row.evidence.get("feature_quote", ""),
            shortlist_rank=row.evidence.get("shortlist_rank"),
            shortlist_size=row.evidence.get("shortlist_size"),
            model=row.model,
            prompt_version=row.prompt_version,
            created_at=row.created_at,
            decided_by=row.decided_by,
            decided_at=row.decided_at,
            decision_note=row.decision_note,
        )

    @app.get("/releases/{name}/link-suggestions", response_model=LinkSuggestionsOut)
    async def list_link_suggestions(name: str, status: str | None = None) -> LinkSuggestionsOut:
        """AI link suggestions for a release. None count as links until a person confirms."""
        from collections import Counter

        from agents.link_store import SuggestionStatus

        v = await view(name)
        key = v.assessment.release.key
        rows = await run_in_threadpool(links().list, key)
        shown = {"suggested", "confirmed", "rejected"}
        if status is not None:
            if status not in shown:
                raise HTTPException(422, f"status must be one of {sorted(shown)}")
            shown = {status}
        return LinkSuggestionsOut(
            release=key,
            counts=dict(Counter(r.status.value for r in rows)),
            cost_usd=round(sum(r.cost_usd for r in rows), 6),
            suggestions=[
                suggestion_out(v, r)
                for r in rows
                if r.status.value in shown and r.status is not SuggestionStatus.NONE
            ],
        )

    async def _decide_link(
        name: str, suggestion_id: int, body: LinkDecisionIn, confirm: bool, who: Actor
    ) -> LinkSuggestionOut:
        from agents.link_store import SuggestionError

        v = await view(name)
        key = v.assessment.release.key
        try:
            row = await run_in_threadpool(
                lambda: links().decide(
                    key,
                    suggestion_id,
                    confirm=confirm,
                    by=who.recorded_as,
                    note=body.note,
                )
            )
        except KeyError as exc:
            raise HTTPException(404, f"suggestion {suggestion_id} not found for {name}") from exc
        except SuggestionError as exc:
            raise HTTPException(409, str(exc)) from exc
        svc().invalidate()  # a confirmed link changes the facts and the forecast
        return suggestion_out(v, row)

    @app.post(
        "/releases/{name}/link-suggestions/{suggestion_id}/confirm",
        response_model=LinkSuggestionOut,
    )
    async def confirm_link(
        name: str, suggestion_id: int, body: LinkDecisionIn, who: Actor = Depends(approver)
    ) -> LinkSuggestionOut:
        """A person confirms: the link becomes verified and counts from now on."""
        return await _decide_link(name, suggestion_id, body, confirm=True, who=who)

    @app.post(
        "/releases/{name}/link-suggestions/{suggestion_id}/reject",
        response_model=LinkSuggestionOut,
    )
    async def reject_link(
        name: str, suggestion_id: int, body: LinkDecisionIn, who: Actor = Depends(approver)
    ) -> LinkSuggestionOut:
        """A person rejects: the suggestion is hidden from the feature for good."""
        return await _decide_link(name, suggestion_id, body, confirm=False, who=who)

    def simulator() -> Any:
        from api.simulation import SimulatorService

        if state["sim"] is None:
            store = state["sim_store"] or _default_sim_store()
            state["sim"] = SimulatorService(store)
        return state["sim"]

    async def sim_state(name: str) -> tuple[ReleaseView, Any, Any]:
        from api.simulation import NoCalibrationError

        v = await view(name)
        try:
            cal, st = await run_in_threadpool(simulator().state, v)
        except NoCalibrationError as exc:
            # Visitors see the detail (#60); the developer hint stays in the log.
            logger.info("no simulator calibration; run make sim-calibrate", extra={"release": name})
            raise HTTPException(404, NO_SIMULATOR.format(name=name)) from exc
        return v, cal, st

    @app.get("/releases/{name}/simulator", response_model=SimulatorOut)
    async def simulator_info(name: str) -> SimulatorOut:
        """Inputs, sources and validation status of the simulator for this release."""
        from collections import Counter

        from simulator.scenario import base_reviewers

        _, cal, st = await sim_state(name)
        c = cal.calibration
        open_now = Counter(p.pool for p in st.in_flight)
        return SimulatorOut(
            release=st.release_key,
            validated=c.validated,
            validation=dict(c.validation),
            calibration_id=cal.id,
            calibrated_at=cal.created_at,
            source_releases=list(c.inputs.source_releases),
            data_until=c.data_until,
            effort_days=c.effort_days,
            as_of=st.as_of,
            horizon_at=st.horizon_at,
            horizon_label=st.horizon_label,
            replications=simulator().replications,
            pools=[
                SimPoolOut(
                    pool=p.name,
                    prs_measured=p.prs,
                    arrivals_per_week=round(p.arrivals_per_week, 2),
                    reviewers_per_week_source=round(p.reviewers_per_week, 2),
                    reviewers_now=base_reviewers(st.staffing, p.name),
                    open_prs_now=open_now.get(p.name, 0),
                    first_wait_median_days=p.first_wait_median_days,
                    follow_wait_median_days=p.follow_wait_median_days,
                    first_scale=c.scales[p.name][0],
                    later_scale=c.scales[p.name][1],
                )
                for p in c.inputs.pools.values()
            ],
            note=sim_note(c.validated),
        )

    async def simulate_out(name: str, body: ScenarioIn) -> SimulationOut:
        from simulator.scenario import PoolChange, Scenario, comparison_to_json

        v, cal, _ = await sim_state(name)
        scenario = Scenario(
            name=body.name or "scenario",
            pools={k: PoolChange(**c.model_dump()) for k, c in body.pools.items()},
            arrival_multiplier=body.arrival_multiplier,
        )
        problems = scenario.problems(list(cal.calibration.inputs.pools))
        if problems:
            raise HTTPException(422, "; ".join(problems))
        sim = await run_in_threadpool(simulator().simulate, v, scenario)
        out = comparison_to_json(sim.comparison)
        return SimulationOut(
            release=sim.state.release_key,
            validated=sim.calibration.calibration.validated,
            calibration_id=sim.calibration.id,
            source_releases=list(sim.calibration.calibration.inputs.source_releases),
            as_of=sim.state.as_of,
            horizon_at=sim.state.horizon_at,
            horizon_label=sim.state.horizon_label,
            replications=out["replications"],
            seed=out["seed"],
            baseline=out["baseline"],
            scenario=out["scenario"],
            seconds=sim.seconds,
            note=sim_note(sim.calibration.calibration.validated),
        )

    @app.post("/releases/{name}/simulate", response_model=SimulationOut)
    async def simulate(name: str, body: ScenarioIn) -> SimulationOut:
        """Run a scenario next to the baseline. Nothing is saved.

        At most ``MAX_PARALLEL_SIMULATIONS`` run at once; more get 429 (security review).
        """
        if simulations.locked():
            raise HTTPException(
                429, "The simulator is busy; try again in a few seconds.", {"Retry-After": "5"}
            )
        async with simulations:
            return await simulate_out(name, body)

    def saved_out(row: Any) -> SavedScenarioOut:
        return SavedScenarioOut(
            id=row.id,
            name=row.name,
            created_by=row.created_by,
            created_at=row.created_at,
            calibration_id=row.calibration_id,
            settings=row.settings,
            result=row.result,
        )

    @app.post("/releases/{name}/scenarios", response_model=SavedScenarioOut, status_code=201)
    async def save_scenario(
        name: str, body: ScenarioIn, who: Actor = Depends(approver)
    ) -> SavedScenarioOut:
        """Run and save a named scenario with its result (409 if the name is taken)."""
        from api.sim_store import ScenarioExistsError

        if not body.name.strip():
            raise HTTPException(422, "a saved scenario needs a name")
        result = await simulate_out(name, body)
        try:
            row = await run_in_threadpool(
                lambda: simulator().store.save_scenario(
                    result.release,
                    result.calibration_id,
                    body.name.strip(),
                    body.model_dump(mode="json"),
                    result.model_dump(mode="json"),
                    who.recorded_as,
                )
            )
        except ScenarioExistsError as exc:
            raise HTTPException(409, f"a scenario named {body.name!r} already exists") from exc
        return saved_out(row)

    @app.get("/releases/{name}/scenarios", response_model=list[SavedScenarioOut])
    async def list_scenarios(name: str) -> list[SavedScenarioOut]:
        """Saved scenarios for the release, newest first."""
        v = await view(name)
        rows = await run_in_threadpool(simulator().store.list_scenarios, v.assessment.release.key)
        return [saved_out(r) for r in rows]

    @app.get("/releases/{name}/scenarios/{scenario_id}", response_model=SavedScenarioOut)
    async def get_scenario(name: str, scenario_id: int) -> SavedScenarioOut:
        """One saved scenario."""
        v = await view(name)
        row = await run_in_threadpool(
            simulator().store.get_scenario, v.assessment.release.key, scenario_id
        )
        if row is None:
            raise HTTPException(404, f"scenario {scenario_id} not found for {name}")
        return saved_out(row)

    @app.get("/releases/{name}/summary", response_model=SummaryOut)
    async def summary(name: str) -> SummaryOut:
        """Dashboard tiles and feature outcomes (computed facts only)."""
        return summary_out(await view(name))

    @app.get("/releases/{name}/graph", response_model=GraphOut)
    async def graph(name: str) -> GraphOut:
        """Release dependency graph: features, verified PR links, stated PR dependencies."""
        return graph_out(await view(name))

    # The dependency graph is the costliest read (about 115 ms and 260 KiB for v1.38, 15x
    # the other pages) and it ran on the event loop, so it delayed every request, /health
    # included: read p95 about 2 s at 13 requests/s (#70). Build it once per release view,
    # off the event loop, and serve the stored JSON until the data changes.
    dependencies_cache: OrderedDict[tuple[Any, ...], bytes] = OrderedDict()

    @app.get("/releases/{name}/dependencies", response_model=DependenciesOut)
    async def dependencies(name: str, include_removed: bool = False) -> Response:
        """Feature-to-feature dependencies: shared PRs, stated "depends on", waiting PRs."""
        v = await view(name)
        key = (v.assessment.release.key, v.version, v.computed_at, include_removed)
        body = dependencies_cache.get(key)
        if body is None:
            body = await run_in_threadpool(
                lambda: dependencies_out(v, include_removed).model_dump_json().encode()
            )
            dependencies_cache[key] = body
            while len(dependencies_cache) > DEPENDENCIES_CACHE_SIZE:
                dependencies_cache.popitem(last=False)
        return Response(content=body, media_type="application/json")

    @app.get("/releases/{name}/merge-dates", response_model=MergeDatesOut)
    async def merge_dates(name: str) -> MergeDatesOut:
        """Days-of-delay chart: when features' required code merges (ranges, ADR-0005)."""
        return merge_dates_out(await view(name))

    @app.get("/releases/{name}/snapshots", response_model=SnapshotsOut)
    async def snapshots(name: str) -> SnapshotsOut:
        """Forecasts recorded each day for this release (append-only; ADR-0015)."""
        v = await view(name)
        store = state["snapshots"] or _default_snapshot_store()
        state["snapshots"] = store
        runs = await run_in_threadpool(store.runs, v.assessment.release.key)
        return SnapshotsOut(
            release=v.assessment.release.key,
            current_model_version=model_version(DEFAULT_FORECAST),
            runs=[
                SnapshotRunOut(
                    snapshot_date=r.snapshot_date,
                    as_of=r.as_of,
                    model_version=r.model_version,
                    features=len(r.features),
                )
                for r in runs
            ],
        )

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
        if open_streams["n"] >= MAX_OPEN_STREAMS:
            # Browsers' EventSource retries by itself; Retry-After spreads the retries.
            raise HTTPException(503, "Too many live pages open; retrying.", {"Retry-After": "30"})
        hub = state["updates"] or _default_updates()
        state["updates"] = hub

        async def events() -> AsyncIterator[str]:
            open_streams["n"] += 1
            try:
                async for chunk in _events():
                    yield chunk
            finally:
                open_streams["n"] -= 1

        async def _events() -> AsyncIterator[str]:
            # Push when the data is newer than what this page last got, whoever refreshed
            # it: comparing against the version before this stream's own refresh missed
            # updates for up to 11 minutes when another page or request refreshed first
            # (2026-11-24).
            last_sent = svc().version
            yield _sse("ready", {"release": name, "version": last_sent})
            yield f"retry: {STREAM_RETRY_MS}\n\n"
            deadline = time.monotonic() + STREAM_MAX_S
            async for notice in hub.subscribe(request.is_disconnected):
                if time.monotonic() >= deadline:
                    return  # the browser reconnects after STREAM_RETRY_MS
                if notice is None:
                    yield ": heartbeat\n\n"
                    continue
                # Continue the trace started by the collector (via queue and worker).
                with tracer.start_as_current_span(
                    "api.push_update", context=notice.context, attributes={"tpm.release": name}
                ):
                    notified = time.monotonic()
                    await run_in_threadpool(svc().refresh)
                    if svc().version == last_sent:
                        continue
                    # Wait for the recomputed view here, in the stream, so the browser
                    # reloads only once the new data is ready (pages never wait for it).
                    v = await view(name, wait=True)
                    if v.version <= last_sent:
                        continue  # another project's events: this release did not change (#70)
                    last_sent = v.version
                    yield _sse(
                        "update",
                        {
                            "release": name,
                            "version": v.version,
                            "as_of": v.assessment.as_of.isoformat(),
                        },
                    )
                    # Event -> dashboard latency. P3-M4 (ADR-0019): from the worker's notice
                    # (sent after the event is stored, batched for DEBOUNCE_S) to the push.
                    # P3-M5: also from the first event's source and collector times.
                    logger.info(
                        "live update pushed",
                        extra={
                            "release": name,
                            "version": v.version,
                            "seconds_since_notified": round(time.monotonic() - notified, 2),
                            "debounce_s": DEBOUNCE_S,
                            **push_timing(notice, datetime.now(UTC)),
                        },
                    )

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    def _program_facts(team: TeamConfig, v: ReleaseView, skipped: list[dict[str, str]]) -> Any:
        """Stored facts for one program. A store that cannot be read is listed, not hidden."""
        from agents.link_store import SuggestionStatus
        from agents.updates import UpdateStatus

        a = v.assessment
        key = a.release.key
        draft, suggested = None, 0
        try:
            rows = ai_services.list_updates(v)
            if rows and rows[0][0].status is UpdateStatus.DRAFT:
                draft = rows[0][0].id
        except Exception:  # one store must not take the page down
            logger.exception("portfolio: updates unavailable for %s", key)
            skipped.append({"team": team.id, "reason": "exec updates could not be read"})
        try:
            suggested = len(links().list(key, SuggestionStatus.SUGGESTED))
        except Exception:
            logger.exception("portfolio: link suggestions unavailable for %s", key)
            skipped.append({"team": team.id, "reason": "link suggestions could not be read"})
        lab = None
        if team.author_lanes:
            r = lab_report(
                v.world,
                key,
                lane_specs(team.author_lanes),
                team.reviewer_pool,
                since=_lab_since(team, v),
            )
            unassigned = sum(b.opened for b in r.buckets if b.lane == "unassigned")
            human = next(
                (s["value"] for s in (r.pod or {}).get("flow", []) if s["stage"] == "human_review"),
                None,
            )
            lab = LabFacts(
                r.n_merged,
                r.approved_merged,
                r.median_hours_to_merge,
                unassigned,
                human_reviewed=human["human_reviewed"] if human else None,
                reviewed_of=human["merged"] if human else None,
                human_approved=human.get("approved")
                if human and human.get("approved_of")
                else None,
            )
        return program_facts(v, team, draft_id=draft, suggested_links=suggested, lab=lab)

    @app.get("/portfolio", response_model=PortfolioOut)
    async def portfolio_view() -> PortfolioOut:
        """Every live program at once (ADR-0025). Deterministic facts only, no AI."""

        def build() -> dict[str, Any]:
            with tracer.start_as_current_span("api.portfolio") as span:
                s = svc()
                facts, skipped = [], []
                for team in load_teams().values():
                    name = s.current_release_name(team.project)
                    if name is None:
                        skipped.append({"team": team.id, "reason": "no release yet"})
                        continue
                    try:
                        v = s.view(f"{team.project}:{name}")
                    except Exception:  # the other programs still return
                        logger.exception("portfolio: %s:%s failed", team.project, name)
                        skipped.append({"team": team.id, "reason": "release could not be computed"})
                        continue
                    facts.append(_program_facts(team, v, skipped))
                span.set_attribute("portfolio.programs", len(facts))
                span.set_attribute("portfolio.skipped", len(skipped))
                return portfolio(facts, skipped, datetime.now(UTC))

        return PortfolioOut.model_validate(await run_in_threadpool(build))

    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,health")
    return app


def _lab_since(team: TeamConfig, v: ReleaseView) -> datetime | None:
    """This repository counts its whole history; other teams count the release cycle."""
    return None if team.project == "tpm-intelligence" else v.assessment.release.cycle_start_at


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _default_service() -> ReleaseService:
    from sqlalchemy.orm import sessionmaker

    from agents.link_store import PostgresLinkSuggestionStore, engine_links
    from api.service import PostgresEventSource
    from api.snapshots import PostgresSnapshotStore, recorder
    from pipeline.store.session import make_engine

    factory = sessionmaker(make_engine())
    links = PostgresLinkSuggestionStore(factory)
    return ReleaseService(
        PostgresEventSource(factory),
        extra_links=lambda key: engine_links(links.list(key)),
        # The day's forecast is recorded once, append-only, for the unseen test (ADR-0015).
        on_computed=recorder(PostgresSnapshotStore(factory)),
    )


def _default_snapshot_store() -> Any:
    from sqlalchemy.orm import sessionmaker

    from api.snapshots import PostgresSnapshotStore
    from pipeline.store.session import make_engine

    return PostgresSnapshotStore(sessionmaker(make_engine()))


def _default_sim_store() -> Any:
    from sqlalchemy.orm import sessionmaker

    from api.sim_store import PostgresSimStore
    from pipeline.store.session import make_engine

    return PostgresSimStore(sessionmaker(make_engine()))


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
    updates: Updates | None = None
    worker_stop: threading.Event | None = None
    if os.getenv("WORKER_IN_PROCESS", "").lower() == "true":
        # Cloud, option B (ADR-0017): the worker runs in this process and announces new
        # events directly, so no worker service and no Redis are needed.
        from api.live import DEBOUNCE_S, InMemoryUpdates
        from pipeline.worker import start_in_background

        local = InMemoryUpdates(debounce_s=DEBOUNCE_S)
        worker_stop = start_in_background(local.publish)
        updates = local
    app = create_app(cors_origins=origins, updates=updates)
    # Warm in the background so the server starts accepting requests at once.
    threading.Thread(target=app.state.warm_on_boot, name="warm-on-boot", daemon=True).start()
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",  # noqa: S104
            port=int(os.getenv("PORT", "8000")),
            log_config=None,
        )
    finally:
        if worker_stop is not None:
            # Stop pulling and hand back what was pulled but not processed, so the next
            # revision gets it at once (P3-M5).
            worker_stop.set()
            for t in threading.enumerate():
                if t.name == "worker":
                    t.join(timeout=10)
        telemetry.shutdown()


if __name__ == "__main__":
    main()
