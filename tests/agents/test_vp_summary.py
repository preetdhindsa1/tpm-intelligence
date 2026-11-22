"""VP summarizer and approval workflow on the real #6395 / #2570 history (fake Claude)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from agents.asks import asks_for
from agents.gateway import Gateway
from agents.ledger import MemoryLedger
from agents.prompts import Prompt
from agents.schemas import ClaimOut, ExecUpdateOut, SectionName, SectionOut
from agents.selection import update_facts
from agents.settings import AISettings
from agents.updates import MemoryUpdateStore, UpdateStatus
from agents.vp_summary import (
    UpdateError,
    decide,
    draft_update,
    edit_update,
    is_stale,
    to_markdown,
    trim,
)
from engine.assess import FeatureAssessment, assess_release
from engine.projection import project
from tests.agents.test_gateway import FakeClient, Response
from tests.engine.conftest import K2570, K6395, MAIN_PR, V138, fixture_events, utc
from verify.build import OddsFacts, build_fact_sheet
from verify.claims import Claim
from verify.facts import FactKind, FactSheet

F = f"feature:{K6395}::"
NOV21 = utc(2026, 11, 21, 3)
PROMPT = Prompt("vp_summary", 1, "Draft the update.")
APPROVER = "Harpreet (local, unauthenticated)"


def state(as_of: datetime = NOV21) -> tuple[list[FeatureAssessment], FactSheet]:
    report = assess_release(project(fixture_events(), as_of), V138)
    odds = {K6395: OddsFacts(0.384, 0.30, 0.46, 0.72, validated=False)}
    return list(report.features), build_fact_sheet(report, odds)


def c(text: str, kind: FactKind, refs: list[str], value: Any) -> ClaimOut:
    return ClaimOut(text=text, type=kind, refs=refs, value=value)


ASK = "Confirm the exception for #143709, or remove the feature from the release."
OUTPUT = ExecUpdateOut(
    sections=[
        SectionOut(
            name=SectionName.SUMMARY,
            claims=[
                c(
                    "Code Freeze was 17 November.",
                    FactKind.DATE,
                    ["release::code_freeze_at"],
                    "2026-11-17",
                )
            ],
        ),
        SectionOut(
            name=SectionName.AT_RISK,
            claims=[
                c(
                    "#6395's main PR was not merged by Code Freeze.",
                    FactKind.BOOLEAN,
                    [F + "flag.main_pr_not_merged"],
                    True,
                ),
                c("Reallocating 3 TPMs would cut risk by 45%.", FactKind.PROBABILITY, [], 0.45),
            ],
        ),
        SectionOut(name=SectionName.REMOVED, claims=[]),
        SectionOut(
            name=SectionName.ASKS,
            claims=[
                c(
                    "Confirm the exception for #143709 or remove the feature.",
                    FactKind.LABEL,
                    [F + "ask.confirm_exception_or_remove"],
                    ASK,
                )
            ],
        ),
    ]
)


def gw(output: ExecUpdateOut = OUTPUT) -> tuple[Gateway, FakeClient]:
    client = FakeClient(Response(parsed_output=output, model="claude-opus-5-5"))
    return Gateway(
        AISettings(), MemoryLedger(), client, clock=lambda: datetime(2026, 11, 21, 4, tzinfo=UTC)
    ), client


# ---------------------------------------------------------------- facts and asks


def test_asks_come_from_rules() -> None:
    features, _ = state()
    f6395 = next(f for f in features if f.key == K6395)
    codes = dict(asks_for(f6395))
    assert codes["confirm_exception_or_remove"] == ASK
    assert "confirm_merge_plan" not in codes  # superseded once freeze has passed


def test_update_facts_rank_and_scope() -> None:
    features, facts = state()
    sheet, at_risk, removed = update_facts(features, facts)
    assert at_risk[0] in {K6395, K2570}
    assert F + "ask.confirm_exception_or_remove" in sheet
    assert f"pr:{MAIN_PR}::merged_at" in sheet
    assert "release::code_freeze_at" in sheet
    assert removed == []  # both were re-added by Nov 21


# ---------------------------------------------------------------- drafting


def test_draft_keeps_only_verified_claims_in_their_sections() -> None:
    features, facts = state()
    gateway, client = gw()
    store = MemoryUpdateStore()
    update = draft_update(
        gateway, store, V138, features, facts, odds_validated=False, prompt=PROMPT
    )
    assert client.calls[0]["model"] == "claude-opus-5-5"  # summary role
    assert update.status is UpdateStatus.DRAFT
    assert [x.text for x in update.sections["at_risk"]] == [
        "#6395's main PR was not merged by Code Freeze."
    ]
    assert len(update.sections["asks"]) == 1
    assert update.removed[0]["reason"] == "no_supporting_data"  # the invented TPM claim
    assert update.header["code_freeze_at"] == "2026-11-17T12:00:00+00:00"
    assert update.header["odds_validated"] is False
    md = to_markdown(update)
    assert "## Asks" in md
    assert "not validated" in md
    assert "Reallocating" not in md


def test_trim_keeps_section_order_within_word_budget() -> None:
    long = Claim(text="word " * 150, type=FactKind.BOOLEAN, refs=("x",), value=True)
    short = Claim(text="short claim", type=FactKind.BOOLEAN, refs=("x",), value=True)
    kept, dropped = trim(
        {"summary": [long], "at_risk": [long, short], "asks": [short]}, max_words=160
    )
    assert [len(v) for v in kept.values()] == [1, 1, 0, 1]
    assert dropped == 1


# ---------------------------------------------------------------- edit and approve


def draft() -> tuple[MemoryUpdateStore, int, list[FeatureAssessment], FactSheet]:
    features, facts = state()
    store = MemoryUpdateStore()
    update = draft_update(
        gw()[0], store, V138, features, facts, odds_validated=False, prompt=PROMPT
    )
    assert update.id is not None
    return store, update.id, features, facts


def test_edit_rechecks_and_approval_needs_acknowledgement() -> None:
    store, uid, _, _ = draft()
    u = store.get(uid)
    assert u is not None
    reworded = Claim(
        text="Code Freeze was 18 November.",
        type=FactKind.DATE,
        refs=("release::code_freeze_at",),
        value="2026-11-17",
    )
    edited = edit_update(store, uid, {"summary": [reworded], "asks": u.sections["asks"]})
    assert edited.edited
    assert edited.sections["at_risk"] == []  # removed by the TPM
    assert [w.reason for w in edited.warnings] == ["text_mismatch"]
    with pytest.raises(UpdateError, match="acknowledge"):
        decide(store, uid, approve=True, approver=APPROVER, stale=False)
    approved = decide(
        store, uid, approve=True, approver=APPROVER, stale=False, acknowledge_warnings=True
    )
    assert approved.status is UpdateStatus.APPROVED
    assert approved.decided_by == APPROVER
    assert approved.approved_with_warnings
    with pytest.raises(UpdateError):
        edit_update(store, uid, {})  # approved updates are frozen


def test_stale_draft_needs_acknowledgement_and_reject_works() -> None:
    store, uid, _, _ = draft()
    with pytest.raises(UpdateError, match="facts changed"):
        decide(store, uid, approve=True, approver=APPROVER, stale=True)
    rejected = decide(
        store, uid, approve=False, approver=APPROVER, stale=True, note="redraft tomorrow"
    )
    assert rejected.status is UpdateStatus.REJECTED
    assert rejected.decision_note == "redraft tomorrow"


def test_staleness_follows_meaningful_fact_changes() -> None:
    store, uid, features, facts = draft()
    u = store.get(uid)
    assert u is not None
    assert not is_stale(u, features, facts)[0]
    later_features, _ = state(utc(2026, 11, 21, 3))
    report = assess_release(project(fixture_events(), utc(2026, 11, 21, 3)), V138)
    moved = build_fact_sheet(report, {K6395: OddsFacts(0.9, 0.8, 0.95, 0.72, validated=False)})
    assert is_stale(u, later_features, moved)[0]
