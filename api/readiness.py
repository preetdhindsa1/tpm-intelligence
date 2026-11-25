"""Readiness and retro endpoints (Wave 5, ADR-0032) on a synthetic fixture.

Until the readiness engine (#181) and retro facts (#182) are wired in, every response says
``"synthetic": true`` and its content is invented for the page to be built against. Decisions
are appended to this process's copy only.
"""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request

from api.readiness_schemas import (
    PatternsOut,
    ReadinessDecisionIn,
    ReadinessDecisionOut,
    ReadinessOut,
    RetroOut,
    SaidVsShowedOut,
)

_T = datetime(2026, 11, 17, 12, tzinfo=UTC)
_SYN = "Synthetic fixture: "


def _criteria() -> list[dict[str, Any]]:
    def c(cid: str, name: str, status: str, detail: str, count: int | None,
          evidence: list[tuple[str, str]]) -> dict[str, Any]:  # fmt: skip
        ev = [{"text": _SYN + t, "ref": r, "url": None} for t, r in evidence]
        return {"id": cid, "name": name, "status": status, "detail": _SYN + detail,
                "count": count, "evidence": ev}  # fmt: skip

    # fmt: off
    return [
        c("code_merged", "Code merged or excepted", "fail",
          "2 features have a main PR that is not merged and has no exception.", 2,
          [("Main PR #144232 is open.", "feature:kubernetes/enhancements#5419")]),
        c("no_critical_flags", "No open critical flags", "fail", "3 critical flags are open.", 3,
          [("Main PR not merged by Code Freeze.", "feature:kubernetes/enhancements#5419")]),
        c("ci_green", "CI green", "pass", "No failing check on the latest commits.", 0, []),
        c("risks_owned", "Every open risk has an owner", "unknown",
          "No confirmed RAID risks yet; suggested items do not count.", None, []),
        c("docs_merged", "Docs merged", "pass", "Every feature's docs PR is merged.", 0, []),
    ]
    # fmt: on


def _retro() -> dict[str, Any]:
    slips = [
        {"feature_key": "kubernetes/enhancements#9001", "title": _SYN + "dropped feature",
         "pool": "sig/node", "slip": "dropped", "slipped_at": _T,
         "first_warning_at": _T - timedelta(days=12), "first_warning_flag": "late_main_pr",
         "lead_time_days": 12.0},
        {"feature_key": "kubernetes/enhancements#9002", "title": _SYN + "late exception",
         "pool": "sig/storage", "slip": "late_exception", "slipped_at": _T + timedelta(days=3),
         "first_warning_at": None, "first_warning_flag": None, "lead_time_days": None},
    ]  # fmt: skip
    return {
        "project": "kubernetes", "release": "v1.37", "label": "Synthetic retro (fixture)",
        "synthetic": True,
        "sources": [{"kind": "snapshots", "title": "Synthetic forecast snapshots", "url": None,
                     "synthetic": True}],
        "totals": {"slips": 2, "warned": 1, "average_lead_time_days": 12.0,
                   "median_lead_time_days": 12.0},
        "slips": slips,
    }  # fmt: skip


def readiness_router(
    approver: Callable[[Request], Awaitable[Any]],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> APIRouter:
    """Readiness and retro endpoints. ``approver`` is the app's sign-in dependency."""
    router = APIRouter(tags=["readiness", "retro"])
    lock = threading.Lock()
    decisions: list[dict[str, Any]] = []

    def readiness(release: str) -> ReadinessOut:
        criteria = _criteria()
        statuses = {c["status"] for c in criteria}
        verdict = (
            "not_ready" if "fail" in statuses else "unknown" if "unknown" in statuses else "ready"
        )
        with lock:
            log = [d for d in decisions if d["release"] == release]
        return ReadinessOut.model_validate({
            "project": "kubernetes", "release": release, "as_of": now(), "synthetic": True,
            "verdict": verdict, "criteria": criteria, "decisions": log, "summary": None,
            "validated": False,
            "validation_note": "Not validated: the readiness backtest has not run (ADR-0032).",
        })  # fmt: skip

    @router.get("/readiness", response_model=ReadinessOut)
    async def get_readiness(release: str = "v1.38") -> ReadinessOut:
        """Each criterion with its evidence, the verdict and the decision log."""
        return readiness(release)

    @router.post("/readiness/{release}/decision", response_model=ReadinessOut, status_code=201)
    async def decide(
        release: str, body: ReadinessDecisionIn, who: Any = Depends(approver)
    ) -> ReadinessOut:
        """Append a person's go/no-go call with a note. Earlier calls are never changed."""
        row = ReadinessDecisionOut(decision=body.decision, note=body.note, decided_by="approver",
                                   decided_at=now(), facts_as_of=now())  # fmt: skip
        with lock:
            decisions.append({**row.model_dump(), "release": release})
        return readiness(release)

    @router.get("/retro", response_model=RetroOut)
    async def get_retro() -> RetroOut:
        """What slipped, and when the platform first warned (as-of replay)."""
        return RetroOut.model_validate({**_retro(), "as_of": now()})

    @router.get("/retro/said-vs-showed", response_model=SaidVsShowedOut)
    async def said_vs_showed() -> SaidVsShowedOut:
        """RAID items from each meeting next to the forecast snapshot of the same date."""
        row = {
            "date": _T - timedelta(days=7),
            "said": [{"item_id": 4, "raid_id": None, "type": "risk",
                      "title": _SYN + "CI flakes on the node e2e job", "review": "suggested"}],
            "showed": [{"name": "features_at_risk", "value": 11},
                       {"name": "critical_flags", "value": 3}],
        }  # fmt: skip
        return SaidVsShowedOut.model_validate(
            {"project": "kubernetes", "release": "v1.37", "synthetic": True, "rows": [row]}
        )

    @router.get("/retro/patterns", response_model=PatternsOut)
    async def patterns() -> PatternsOut:
        """Patterns per pool across releases; groups under 10 are counted, not shown."""
        p = {"pool": "sig/node", "pattern": "late_main_pr",
             "text": _SYN + "main PRs opened in the last 14 days before Code Freeze",
             "value": 0.4, "n": 25, "releases": ["v1.36", "v1.37"]}  # fmt: skip
        return PatternsOut.model_validate({"project": "kubernetes", "synthetic": True,
                                           "min_group": 10, "suppressed_groups": 4,
                                           "patterns": [p]})  # fmt: skip

    return router
