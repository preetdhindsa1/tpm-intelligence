"""Risk analyst agent: why is this feature at risk? Generated when its page is opened.

The owner chose on-demand generation (2026-11-22): nothing runs in the background. A stored
note is reused until the feature's facts change meaningfully (agents/rerun.py) or the
prompt changes. Only verified claims are stored or shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agents.gateway import AIError, BudgetExceededError, Gateway, TaskSpec
from agents.loop import run_loop
from agents.notes import NoteStore, RiskNote
from agents.prompts import Prompt, load_prompt
from agents.rerun import changed_meaningfully
from agents.selection import feature_facts, is_at_risk
from agents.settings import ModelRole
from engine.assess import FeatureAssessment
from verify.facts import FactSheet

TASK = TaskSpec("risk_analyst", ModelRole.SIMPLE, effort="low", max_tokens=4000, essential=False)


class NoteStatus(StrEnum):
    """Outcome of a request for a risk note."""

    NOT_AT_RISK = "not_at_risk"
    FRESH = "fresh"  # generated now
    REUSED = "reused"  # stored note still matches the facts
    STALE = "stale"  # facts changed but a new note could not be made (budget/error)
    PAUSED = "paused"  # budget blocked and no note exists yet
    FAILED = "failed"  # AI error and no note exists yet
    SIGN_IN_REQUIRED = "sign_in_required"  # a new note needs paid AI; only approvers can


@dataclass(frozen=True)
class NoteResult:
    """What the API returns."""

    status: NoteStatus
    note: RiskNote | None = None
    reason: str | None = None


def risk_note(
    gateway: Gateway,
    store: NoteStore,
    release_key: str,
    feature: FeatureAssessment,
    release_facts: FactSheet,
    prompt: Prompt | None = None,
    *,
    generate: bool = True,
) -> NoteResult:
    """Return a verified note for an at-risk feature, generating one only if needed.

    With ``generate=False`` (visitors who are not approvers, ADR-0016) Claude is never
    called: a stored note is returned, marked stale if the facts have moved on.
    """
    if not is_at_risk(feature, release_facts):
        return NoteResult(NoteStatus.NOT_AT_RISK)
    prompt = prompt or load_prompt("risk_analyst")
    facts = feature_facts(feature, release_facts)
    previous = store.latest(release_key, feature.key)
    if previous is not None and previous.prompt_version == prompt.label:
        changed, why = changed_meaningfully(
            previous.facts, facts, odds_change_points=gateway.settings.odds_change_points
        )
        if not changed:
            return NoteResult(NoteStatus.REUSED, previous, why)
    if not generate:
        if previous is not None:
            return NoteResult(NoteStatus.STALE, previous, "an approver can refresh it")
        return NoteResult(NoteStatus.SIGN_IN_REQUIRED, None, "sign in as an approver to generate")
    try:
        result = run_loop(gateway, TASK, prompt, facts)
    except BudgetExceededError as exc:
        status = NoteStatus.STALE if previous else NoteStatus.PAUSED
        return NoteResult(status, previous, f"AI budget: {exc.decision.reason}")
    except AIError as exc:
        status = NoteStatus.STALE if previous else NoteStatus.FAILED
        return NoteResult(status, previous, str(exc))
    note = RiskNote(
        release_key=release_key,
        feature_key=feature.key,
        prompt_version=prompt.label,
        model=result.best.model,
        facts=facts,
        claims=result.claims,
        counts=result.best.report.counts,
        attempts=len(result.attempts),
        cost_usd=result.cost_usd,
    )
    store.save(note)
    return NoteResult(NoteStatus.FRESH, note)
