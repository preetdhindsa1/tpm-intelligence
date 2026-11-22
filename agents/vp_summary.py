"""VP summarizer: draft an executive update; a TPM edits and approves it (M3b).

Drafting is essential AI work (a person asked for it). Only verified claims enter a draft.
The header is computed by code. The platform never sends the update anywhere: approval
records who approved it and when, and the TPM copies it out.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from agents.gateway import Gateway, TaskSpec
from agents.loop import run_loop
from agents.prompts import Prompt, load_prompt
from agents.rerun import changed_meaningfully
from agents.schemas import ExecUpdateOut, SectionName
from agents.selection import is_at_risk, update_facts
from agents.settings import ModelRole
from agents.updates import ClaimWarning, ExecUpdate, UpdateStatus, UpdateStore
from engine.assess import FeatureAssessment
from verify.checker import CheckReport, Verdict, check_claim
from verify.claims import Claim
from verify.facts import FactSheet

TASK = TaskSpec("vp_summary", ModelRole.SUMMARY, effort="medium", max_tokens=8000, essential=True)
MAX_WORDS = 220  # "at most about 200 words" (owner, 2026-11-22), with a small allowance
SECTION_ORDER = [s.value for s in SectionName]


class UpdateError(Exception):
    """A workflow rule was broken (wrong state, unacknowledged warnings, ...)."""


def header_for(facts: FactSheet, at_risk_total: int, odds_validated: bool) -> dict[str, Any]:
    """Release, dates and counts: computed by code, shown above the AI sections."""

    def value(key: str) -> Any:
        f = facts.get(key)
        return (
            None
            if f is None
            else (f.value.isoformat() if isinstance(f.value, datetime) else f.value)
        )

    return {
        "release": value("release::name"),
        "data_as_of": value("release::as_of"),
        "code_freeze_at": value("release::code_freeze_at"),
        "release_at": value("release::release_at"),
        "features_in_release": value("release::features_in_release"),
        "features_removed": value("release::features_removed"),
        "features_at_risk": at_risk_total,
        "odds_validated": odds_validated,
    }


def verified_sections(output: ExecUpdateOut, report: CheckReport) -> dict[str, list[Claim]]:
    """Map each verified claim back to its section (the report keeps claim order)."""
    checked = iter(report.checked)
    sections: dict[str, list[Claim]] = {name: [] for name in SECTION_ORDER}
    for section in output.sections:
        for _ in section.claims:
            c = next(checked)
            if c.verdict is Verdict.VERIFIED:
                sections[section.name.value].append(c.claim)
    return sections


def trim(
    sections: dict[str, list[Claim]], max_words: int = MAX_WORDS
) -> tuple[dict[str, list[Claim]], int]:
    """Keep claims in section order until the word budget is used; return (kept, dropped)."""
    kept: dict[str, list[Claim]] = {name: [] for name in SECTION_ORDER}
    words, dropped = 0, 0
    for name in SECTION_ORDER:
        for claim in sections.get(name, []):
            n = len(claim.text.split())
            if words + n > max_words:
                dropped += 1
                continue
            kept[name].append(claim)
            words += n
    return kept, dropped


def draft_update(
    gateway: Gateway,
    store: UpdateStore,
    release_key: str,
    features: list[FeatureAssessment],
    release_facts: FactSheet,
    *,
    odds_validated: bool,
    prompt: Prompt | None = None,
) -> ExecUpdate:
    """Ask Claude for a draft, keep verified claims, store it as a draft."""
    prompt = prompt or load_prompt("vp_summary")
    facts, at_risk_keys, removed_keys = update_facts(features, release_facts)
    at_risk_total = sum(1 for f in features if is_at_risk(f, release_facts))
    result = run_loop(
        gateway,
        TASK,
        prompt,
        facts,
        extra_inputs={"at_risk_order": at_risk_keys, "removed_at_freeze": removed_keys},
        output_model=ExecUpdateOut,
    )
    output = result.best.output
    assert isinstance(output, ExecUpdateOut)  # noqa: S101 - run_loop was given this model
    sections, dropped = trim(verified_sections(output, result.best.report))
    as_of = facts.get("release::as_of")
    update = ExecUpdate(
        release_key=release_key,
        as_of=as_of.value
        if as_of is not None and isinstance(as_of.value, datetime)
        else datetime.now(UTC),
        header=header_for(facts, at_risk_total, odds_validated),
        sections=sections,
        facts=facts,
        counts=result.best.report.counts,
        removed=[
            {
                "text": c.claim.text,
                "reason": c.reason.value if c.reason else None,
                "detail": c.detail,
            }
            for c in result.best.report.checked
            if c.verdict is Verdict.REMOVED
        ],
        attempts=len(result.attempts),
        model=result.best.model,
        prompt_version=prompt.label,
        cost_usd=result.cost_usd,
        trimmed_for_length=dropped,
    )
    return store.add(update)


def is_stale(
    update: ExecUpdate, features: list[FeatureAssessment], release_facts: FactSheet
) -> tuple[bool, str]:
    """Have the facts behind this update changed meaningfully since it was drafted?"""
    current, _, _ = update_facts(features, release_facts)
    return changed_meaningfully(update.facts, current)


def edit_update(store: UpdateStore, update_id: int, sections: dict[str, list[Claim]]) -> ExecUpdate:
    """Replace a draft's claims (remove or reword) and re-check each against its facts."""
    update = _get(store, update_id)
    if update.status is not UpdateStatus.DRAFT:
        raise UpdateError(f"update {update_id} is {update.status.value}; only drafts can be edited")
    unknown = set(sections) - set(SECTION_ORDER)
    if unknown:
        raise UpdateError(f"unknown section(s): {', '.join(sorted(unknown))}")
    warnings = [
        ClaimWarning(name, c.text, checked.reason.value, checked.detail)
        for name, claims in sections.items()
        for c in claims
        if (checked := check_claim(c, update.facts)).reason is not None
    ]
    edited = replace(
        update,
        sections={name: sections.get(name, []) for name in SECTION_ORDER},
        edited=True,
        warnings=warnings,
    )
    store.save(edited)
    return edited


def decide(
    store: UpdateStore,
    update_id: int,
    *,
    approve: bool,
    approver: str,
    stale: bool,
    acknowledge_warnings: bool = False,
    acknowledge_stale: bool = False,
    note: str | None = None,
) -> ExecUpdate:
    """Approve or reject a draft. Approval over warnings or stale facts must be acknowledged."""
    update = _get(store, update_id)
    if update.status is not UpdateStatus.DRAFT:
        raise UpdateError(f"update {update_id} is already {update.status.value}")
    if approve and update.warnings and not acknowledge_warnings:
        raise UpdateError(
            f"{len(update.warnings)} edited claim(s) fail the fact check; acknowledge to approve"
        )
    if approve and stale and not acknowledge_stale:
        raise UpdateError("facts changed since this draft; redraft or acknowledge to approve")
    decided = replace(
        update,
        status=UpdateStatus.APPROVED if approve else UpdateStatus.REJECTED,
        decided_by=approver,
        decided_at=datetime.now(UTC),
        decision_note=note,
        approved_with_warnings=approve and bool(update.warnings),
        approved_while_stale=approve and stale,
    )
    store.save(decided)
    return decided


def to_markdown(update: ExecUpdate) -> str:
    """Plain Markdown for copying out (the platform never sends it)."""
    h = update.header
    titles = {
        "summary": "Summary",
        "at_risk": "At risk",
        "removed": "Removed at Code Freeze",
        "asks": "Asks",
    }
    lines = [
        f"# {h.get('release')} release update",
        "",
        f"Data as of {h.get('data_as_of')} · Code Freeze {h.get('code_freeze_at')} · "
        f"Release {h.get('release_at')}",
        f"{h.get('features_in_release')} features in the release · "
        f"{h.get('features_at_risk')} at risk · {h.get('features_removed')} removed",
    ]
    if not h.get("odds_validated"):
        lines.append("Odds are not validated against past releases; read them as indicative.")
    for name in SECTION_ORDER:
        claims = update.sections.get(name, [])
        if claims:
            lines += ["", f"## {titles[name]}", *[f"- {c.text}" for c in claims]]
    status = update.status.value
    if update.status is UpdateStatus.APPROVED:
        when = update.decided_at.strftime("%Y-%m-%d %H:%M") if update.decided_at else "?"
        status = f"approved by {update.decided_by} on {when} UTC"
    lines += ["", f"_Every statement was checked against the data before review; {status}._"]
    return "\n".join(lines) + "\n"


def _get(store: UpdateStore, update_id: int) -> ExecUpdate:
    update = store.get(update_id)
    if update is None:
        raise KeyError(update_id)
    return update
