"""Link suggester, job and review store with a fake Claude client (no API calls)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from agents.gateway import Gateway
from agents.ledger import MemoryLedger, UsageRecord
from agents.link_job import suggest_for_release
from agents.link_store import (
    LinkSuggestion,
    MemoryLinkSuggestionStore,
    SuggestionError,
    SuggestionStatus,
    engine_links,
)
from agents.link_suggester import LinkPickOut, PullRequestText, suggest_link, suggester_inputs
from agents.pricing import TokenUsage
from agents.prompts import Prompt
from agents.settings import AISettings
from engine.links import link_release
from engine.projection import World, project
from linker.candidates import Candidate, FeatureDoc
from linker.methods import LinkMethod, LinkStatus
from tests.agents.test_gateway import FakeClient, Response
from tests.engine.conftest import K6395, MAIN_PR, V138, fixture_events, utc

PROMPT = Prompt("link_suggester", 1, "Pick a feature.")
NEW = "kubernetes/kubernetes#150000"
NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)
PICK = LinkPickOut(
    feature_key=K6395,
    pr_quote="mount ephemeral volumes into running pods",
    feature_quote="ephemeral volumes",
)


def gw(response: Response | None = None, ledger: MemoryLedger | None = None) -> Gateway:
    client = FakeClient(response or Response(parsed_output=PICK))
    return Gateway(AISettings(), ledger or MemoryLedger(), client, clock=lambda: NOW)


def world(title: str = "kubelet: mount ephemeral volumes into running pods") -> World:
    w = project(fixture_events(), utc(2026, 11, 22))
    pr = replace(w.pull_requests[MAIN_PR], key=NEW, number=150000, title=title, body="")
    return replace(w, pull_requests={**w.pull_requests, NEW: pr})


DOC = FeatureDoc(K6395, "Dynamic node-local ephemeral volumes", "", (), ("sig/node",))
CANDS = [Candidate(DOC, 1, 2.0, ("ephemeral",), ())]
PR = PullRequestText(NEW, "kubelet: mount ephemeral volumes into running pods", "", ())


def test_input_is_only_the_pr_and_the_shortlist() -> None:
    inputs = suggester_inputs(PR, CANDS)
    assert set(inputs) == {"pull_request", "candidates"}
    assert inputs["candidates"][0]["key"] == K6395


def test_checked_answer_is_kept_with_its_evidence() -> None:
    result = suggest_link(gw(), PROMPT, PR, CANDS)
    assert result.checked.feature_key == K6395
    assert result.evidence()["pr_quote"] == PICK.pr_quote
    assert result.evidence()["shortlist_rank"] == 1


def test_invented_feature_is_dropped() -> None:
    bad = PICK.model_copy(update={"feature_key": "kubernetes/enhancements#1"})
    result = suggest_link(gw(Response(parsed_output=bad)), PROMPT, PR, CANDS)
    assert result.checked.outcome.value == "dropped"


def test_job_stores_suggestions_and_skips_repeat_work() -> None:
    store = MemoryLinkSuggestionStore()
    report = suggest_for_release(gw(), store, world(), V138, prompt=PROMPT, workers=1)
    assert report.counts["suggested"] == 1
    (row,) = store.rows
    assert (row.pull_request_key, row.feature_key, row.status) == (
        NEW,
        K6395,
        SuggestionStatus.SUGGESTED,
    )
    again = suggest_for_release(gw(), store, world(), V138, prompt=PROMPT, workers=1)
    assert again.counts["already_done"] == 1
    assert len(store.rows) == 1


def test_job_makes_no_call_without_candidates() -> None:
    client_gw = gw()
    report = suggest_for_release(
        client_gw,
        MemoryLinkSuggestionStore(),
        world("bump golang.org/x/net"),
        V138,
        prompt=PROMPT,
        workers=1,
    )
    assert report.counts["no_candidates"] == 1
    assert client_gw.client.calls == []  # type: ignore[attr-defined]


def test_job_stops_when_the_budget_pauses_it() -> None:
    ledger = MemoryLedger()
    ledger.record(
        UsageRecord(
            task="x",
            prompt_version="x.v1",
            model_requested="claude-opus-5-5",
            essential=True,
            outcome="ok",
            fingerprint="f",
            usages=(TokenUsage("claude-opus-5-5", 600_000, 0),),
            at=NOW - timedelta(hours=1),
        )
    )
    store = MemoryLinkSuggestionStore()
    report = suggest_for_release(gw(ledger=ledger), store, world(), V138, prompt=PROMPT, workers=1)
    assert report.stopped is not None
    assert report.counts["left_for_later"] == 1
    assert store.rows == []


def row(status: SuggestionStatus, pr: str = NEW, sid: int = 1) -> LinkSuggestion:
    return LinkSuggestion(
        release_key=V138,
        pull_request_key=pr,
        feature_key=K6395,
        status=status,
        evidence={"pr_quote": "q", "feature_quote": "f"},
        input_sha="s",
        prompt_version="link_suggester.v1",
        model="claude-haiku-5-5",
        cost_usd=0.0004,
        id=sid,
        decided_by="user:Harpreet (local, unauthenticated)"
        if status in (SuggestionStatus.CONFIRMED, SuggestionStatus.REJECTED)
        else None,
    )


def test_engine_links_map_statuses() -> None:
    (c,) = engine_links([row(SuggestionStatus.CONFIRMED)])
    assert (c.status, c.method) == (LinkStatus.VERIFIED, LinkMethod.AI_SUGGESTED)
    assert c.evidence["verified_by"].startswith("user:")
    (c,) = engine_links([row(SuggestionStatus.SUGGESTED)])
    assert c.status is LinkStatus.SUGGESTED
    none = replace(row(SuggestionStatus.NONE), feature_key=None)
    assert engine_links([none]) == []


def test_a_decision_beats_a_later_pending_suggestion() -> None:
    later = replace(row(SuggestionStatus.SUGGESTED, sid=2), created_at=NOW + timedelta(days=1))
    (c,) = engine_links([row(SuggestionStatus.REJECTED), later])
    assert c.status is LinkStatus.REJECTED


def test_confirmed_suggestion_counts_in_the_engine() -> None:
    store = MemoryLinkSuggestionStore()
    suggest_for_release(gw(), store, world(), V138, prompt=PROMPT, workers=1)
    store.decide(V138, 1, confirm=True, by="user:Harpreet (local, unauthenticated)")
    w = replace(world(), extra_links=tuple(engine_links(store.rows)))
    assert NEW in link_release(w, V138).verified_prs(K6395)


def test_only_suggested_rows_can_be_decided() -> None:
    store = MemoryLinkSuggestionStore()
    store.save(row(SuggestionStatus.SUGGESTED))
    store.decide(V138, 1, confirm=False, by="user:x", note="different KEP")
    assert store.rows[0].status is SuggestionStatus.REJECTED
    assert store.rows[0].decision_note == "different KEP"
    with pytest.raises(SuggestionError):
        store.decide(V138, 1, confirm=True, by="user:x")
    with pytest.raises(KeyError):
        store.decide("kubernetes:v1.37", 1, confirm=True, by="user:x")
