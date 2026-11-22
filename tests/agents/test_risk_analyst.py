"""Risk analyst on the real #6395 history, with a fake Claude client (no API calls)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from agents.gateway import Gateway
from agents.ledger import MemoryLedger, UsageRecord
from agents.notes import MemoryNoteStore
from agents.pricing import TokenUsage
from agents.prompts import Prompt
from agents.risk_analyst import NoteStatus, risk_note
from agents.schemas import ClaimOut, ClaimsOut
from agents.selection import critical_flag_keys, feature_facts, is_at_risk
from agents.settings import AISettings
from engine.assess import FeatureAssessment, assess_release
from engine.projection import project
from tests.agents.test_gateway import FakeClient, Response
from tests.engine.conftest import K6395, MAIN_PR, V138, fixture_events, utc
from verify.build import OddsFacts, build_fact_sheet
from verify.facts import FactKind, FactSheet

F = f"feature:{K6395}::"
NOV10 = utc(2026, 11, 10)
PROMPT = Prompt("risk_analyst", 1, "Explain the risk.")


def state(as_of: datetime, probability: float = 0.384) -> tuple[FeatureAssessment, FactSheet]:
    report = assess_release(project(fixture_events(), as_of), V138)
    odds = {K6395: OddsFacts(probability, 0.30, 0.46, 0.72, validated=False)}
    feature = next(f for f in report.features if f.key == K6395)
    return feature, build_fact_sheet(report, odds)


GOOD = ClaimsOut(
    claims=[
        ClaimOut(
            text=f"The main PR #{MAIN_PR.split('#')[1]} opened 15 days before Code Freeze.",
            type=FactKind.DURATION_DAYS,
            refs=[F + "flag.late_main_pr.days_before_freeze"],
            value=15,
        ),
        ClaimOut(
            text="Odds of landing are 38% and are not validated.",
            type=FactKind.PROBABILITY,
            refs=[F + "odds.probability", F + "odds.validated"],
            value=0.38,
        ),
    ]
)
BAD = ClaimsOut(
    claims=[
        ClaimOut(text="Reviewers are overloaded.", type=FactKind.BOOLEAN, refs=[], value=True),
        ClaimOut(
            text="Odds are 90%.",
            type=FactKind.PROBABILITY,
            refs=[F + "odds.probability"],
            value=0.9,
        ),
        GOOD.claims[0],
    ]
)


class Sequenced(FakeClient):
    """Returns the given outputs in order."""

    def __init__(self, *outputs: ClaimsOut) -> None:
        super().__init__()
        self.outputs = list(outputs)

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return Response(parsed_output=self.outputs[min(len(self.calls), len(self.outputs)) - 1])


def gw(client: FakeClient, ledger: MemoryLedger | None = None) -> Gateway:
    return Gateway(
        AISettings(),
        ledger or MemoryLedger(),
        client,
        clock=lambda: datetime(2026, 11, 10, 12, tzinfo=UTC),
    )


# ---------------------------------------------------------------- selection


def test_6395_is_at_risk_on_nov_10_and_not_while_removed() -> None:
    feature, facts = state(NOV10)
    assert is_at_risk(feature, facts)  # late_main_pr warning
    removed, removed_facts = state(utc(2026, 11, 18))
    assert not is_at_risk(removed, removed_facts)  # out of the release: nothing to explain


def test_feature_facts_are_scoped_to_the_feature() -> None:
    feature, facts = state(NOV10)
    sub = feature_facts(feature, facts)
    assert "release::code_freeze_at" in sub
    assert F + "flag.late_main_pr" in sub
    assert f"pr:{MAIN_PR}::created_at" in sub
    sig_keys = [k for k in sub if k.startswith("sig:")]
    assert all(k.split("::")[0].removeprefix("sig:") in feature.teams for k in sig_keys)
    assert not any(k.startswith("feature:kubernetes/enhancements#2570::") for k in sub)


def test_critical_flags_must_be_cited_after_freeze() -> None:
    feature, _ = state(utc(2026, 11, 21, 3))
    assert F + "flag.removed_at_freeze" in critical_flag_keys(feature)


# ---------------------------------------------------------------- the agent


def test_good_draft_is_stored_with_only_verified_claims() -> None:
    feature, facts = state(NOV10)
    client, store = Sequenced(GOOD), MemoryNoteStore()
    result = risk_note(gw(client), store, V138, feature, facts, PROMPT)
    assert result.status is NoteStatus.FRESH
    assert result.note is not None
    assert len(result.note.claims) == 2
    assert result.note.attempts == 1
    assert len(client.calls) == 1


def test_bad_draft_is_retried_once_with_feedback() -> None:
    feature, facts = state(NOV10)
    client = Sequenced(BAD, GOOD)
    result = risk_note(gw(client), MemoryNoteStore(), V138, feature, facts, PROMPT)
    assert result.note is not None
    assert result.note.attempts == 2
    assert len(result.note.claims) == 2  # the better attempt wins
    second_input = client.calls[1]["messages"][0]["content"]
    assert "previous_attempt_removed" in second_input
    assert "no_supporting_data" in second_input


def test_never_more_than_two_attempts() -> None:
    feature, facts = state(NOV10)
    client = Sequenced(BAD, BAD, BAD)
    result = risk_note(gw(client), MemoryNoteStore(), V138, feature, facts, PROMPT)
    assert len(client.calls) == 2
    assert result.note is not None
    assert [c.text for c in result.note.claims] == [GOOD.claims[0].text]


def test_note_is_reused_until_facts_change_meaningfully() -> None:
    feature, facts = state(NOV10)
    client, store = Sequenced(GOOD), MemoryNoteStore()
    risk_note(gw(client), store, V138, feature, facts, PROMPT)
    _, jitter = state(NOV10, probability=0.42)  # 4 points: same note
    assert risk_note(gw(client), store, V138, feature, jitter, PROMPT).status is NoteStatus.REUSED
    _, moved = state(NOV10, probability=0.55)  # 17 points: new note
    assert risk_note(gw(client), store, V138, feature, moved, PROMPT).status is NoteStatus.FRESH
    # 1 call for the first note; 2 for the new one, because the fake still says "38%",
    # which is now wrong, so the checker removes it and the loop retries once.
    assert len(client.calls) == 3


def test_prompt_change_regenerates() -> None:
    feature, facts = state(NOV10)
    client, store = Sequenced(GOOD), MemoryNoteStore()
    risk_note(gw(client), store, V138, feature, facts, PROMPT)
    v2 = Prompt("risk_analyst", 2, "Explain the risk, v2.")
    assert risk_note(gw(client), store, V138, feature, facts, v2).status is NoteStatus.FRESH


def test_budget_exhausted_pauses_or_serves_stale() -> None:
    feature, facts = state(NOV10)
    ledger = MemoryLedger()
    ledger.record(
        UsageRecord(
            "x", "p", "m", False, "ok", "f",
            usages=(TokenUsage("claude-opus-5-5", output_tokens=100_000),),
            at=datetime(2026, 11, 10, 11, tzinfo=UTC),
        )
    )  # fmt: skip
    store = MemoryNoteStore()
    paused = risk_note(gw(Sequenced(GOOD), ledger), store, V138, feature, facts, PROMPT)
    assert paused.status is NoteStatus.PAUSED
    assert paused.reason is not None
    assert "budget" in paused.reason

    risk_note(gw(Sequenced(GOOD)), store, V138, feature, facts, PROMPT)  # a note exists now
    _, moved = state(NOV10, probability=0.60)
    stale = risk_note(gw(Sequenced(GOOD), ledger), store, V138, feature, moved, PROMPT)
    assert stale.status is NoteStatus.STALE
    assert stale.note is not None


@pytest.mark.parametrize("as_of", [utc(2026, 11, 18)])
def test_not_at_risk_makes_no_call(as_of: datetime) -> None:
    feature, facts = state(as_of)
    client = Sequenced(GOOD)
    assert (
        risk_note(gw(client), MemoryNoteStore(), V138, feature, facts, PROMPT).status
        is NoteStatus.NOT_AT_RISK
    )
    assert client.calls == []
