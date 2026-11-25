"""RAID job over stored meetings, with a fake Claude client; roster and team detection."""

from __future__ import annotations

from datetime import UTC, datetime

from agents.gateway import BudgetExceededError, Gateway
from agents.ledger import MemoryLedger
from agents.prompts import Prompt
from agents.raid_extractor import ExtractionOut
from agents.raid_job import run_release
from agents.settings import AISettings
from modules.raid.notes import drop_roster, teams_in
from modules.raid.store import MemoryRaidStore
from tests.agents.test_gateway import FakeClient, Response

NOW = datetime(2026, 11, 25, 12, tzinfo=UTC)
PROMPT = Prompt("raid_extractor", 2, "List RAID items.")
TEXT = """Week 12 - Wednesday 18 November 2026 Weekly Meeting (recording)
Host:
      APAC: Jane Roe (she/her)
Attendees (pronouns, release team role):
* Jane Roe (she/her, Enhancements Shadow)
* Sam Poe (he/him, Release Docs Lead)
Updates:
* Release Signal (APAC: Jane Roe / @jroe | EMEA: Sam Poe / @spoe):
   * 3 flakes on master-informing, KEP-6395 among them.
* Docs (APAC: Sam Poe):
   * Sam will chase the remaining draft docs PRs this week.
"""
PAYLOAD = {"container": "doc-1", "meeting_date": "2026-11-18", "text": TEXT}


def gw(items: list[dict] | Exception) -> Gateway:
    out = items if isinstance(items, Exception) else ExtractionOut.model_validate({"items": items})
    client = FakeClient(out if isinstance(out, Exception) else Response(parsed_output=out))
    return Gateway(AISettings(), MemoryLedger(), client, clock=lambda: NOW)


def test_roster_lines_are_removed_and_teams_come_from_headings() -> None:
    text = drop_roster(TEXT)
    assert "Enhancements Shadow" not in text
    assert "Host:" not in text
    assert "3 flakes on master-informing" in text
    assert teams_in([text.replace("Jane Roe", "[participant]")])[:2] == ["Release Signal", "Docs"]


def test_a_run_suggests_counts_and_a_rerun_adds_nothing() -> None:
    flakes = "3 flakes on master-informing, KEP-6395 among them."
    chase = "[participant] will chase the remaining draft docs PRs this week."
    items = [
        {"type": "issue", "title": "Flakes", "quote": flakes, "owner": "Release Signal"},
        {"type": "action", "title": "Chase docs", "quote": chase, "owner": "Docs"},
        {
            "type": "risk",
            "title": "Made up",
            "quote": "Docs Freeze will certainly slip.",
            "owner": None,
        },
    ]
    store = MemoryRaidStore()
    report = run_release(gw(items), PROMPT, [PAYLOAD], "kubernetes:v1.38", "K8S", store, NOW)
    assert (report.meetings, report.returned, report.kept, report.new) == (1, 3, 2, 2)
    assert report.dropped == {"quote_not_found": 1}
    assert (report.with_owner, report.with_links) == (2, 1)
    assert dict(report.by_type) == {"issue": 1, "action": 1}
    stored = store.items("kubernetes:v1.38")
    assert {i.review for i in stored} == {"suggested"}
    assert all("Sam" not in i.quote and "Jane" not in i.quote for i in stored)
    again = run_release(gw(items), PROMPT, [PAYLOAD], "kubernetes:v1.38", "K8S", store, NOW)
    assert (again.kept, again.new) == (2, 0)


def test_the_budget_pause_stops_the_run_and_is_reported() -> None:
    from agents.budget import BudgetDecision, BudgetState

    decision = BudgetDecision(False, BudgetState.PAUSED, "paused: daily AI budget reached")
    pause = BudgetExceededError(decision)
    report = run_release(
        gw(pause), PROMPT, [PAYLOAD], "kubernetes:v1.38", "K8S", MemoryRaidStore(), NOW
    )
    assert report.meetings == 0
    assert len(report.errors) == 1
    assert "budget" in report.errors[0]
