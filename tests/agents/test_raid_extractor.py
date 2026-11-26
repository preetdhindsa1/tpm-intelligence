"""RAID extractor and name masking, with a fake Claude client (no API calls).

The notes excerpt is shaped like the public Kubernetes v1.38 release-team meeting notes
(Week 12, 18 November 2026) and the v1.37 retro, with made-up names.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agents.gateway import Gateway
from agents.ledger import MemoryLedger
from agents.prompts import Prompt, load_prompt
from agents.raid_extractor import (
    ExtractedItemOut,
    ExtractionOut,
    Meeting,
    extract,
    links_in,
    store_all,
)
from agents.settings import AISettings
from modules.raid.mask import MASK, mask_names, names_in
from modules.raid.store import MemoryRaidStore
from tests.agents.test_gateway import FakeClient, Response

NOW = datetime(2026, 11, 25, 12, tzinfo=UTC)
PROMPT = Prompt("raid_extractor", 1, "List RAID items.")
TEAMS = ["Enhancements", "Release Signal", "Docs", "Comms", "Release Branch Management"]
NOTES = """Attendees (pronouns, release team role):
* Jane Roe (she/her, Enhancements Shadow)
* Alex Doe (he/him, Release Comms Shadow)
Updates:
* Enhancements (APAC: Jane Roe / @Jane Roe | EMEA: Sam Poe / @spoe88):
   * In review the code freeze exception requests with Release Lead.
* Comms (APAC/EMEA: Alex Doe / @adoe):
   * Mid cycle blog: Alex has raised the PR (kubernetes/website#59188) for review.
   * [Flaking Test] [sig-node] Pod Allocated Endpoint should return all allocated pods
* Release Branch Management (Robin Moe / @rmoe):
   * We'll start planning for rc.0 soon, rc.0 is on Thursday 3rd December 2026
   * KEP-6395 was removed at Code Freeze and needs an exception.
   * CNCF: We've emailed webinars@cncf.io to schedule the release webinar.
"""
RETRO = "* [Kim + Lee] Exception requests arrived   too late this cycle.\n"
MEETING = Meeting("doc-1", "kubernetes:v1.38", "K8S", "2026-11-18", NOTES)


def item(type_: str, quote: str, owner: str | None = None) -> ExtractedItemOut:
    return ExtractedItemOut.model_validate(
        {"type": type_, "title": "t", "quote": quote, "owner": owner}
    )


def run(items: list[ExtractedItemOut], text: str = NOTES) -> tuple:
    client = FakeClient(Response(parsed_output=ExtractionOut(items=items)))
    gw = Gateway(AISettings(), MemoryLedger(), client, clock=lambda: NOW)
    meeting = Meeting("doc-1", "kubernetes:v1.38", "K8S", "2026-11-18", text)
    names = names_in(text)
    return extract(gw, PROMPT, meeting, names, TEAMS), client


def test_names_come_from_attendees_headings_and_speaker_tags() -> None:
    names = names_in(NOTES + RETRO)
    assert {"Jane Roe", "Alex", "Sam Poe", "Robin Moe", "Kim"} <= names
    assert not {"Release", "APAC", "EMEA", "Flaking Test", "sig-node"} & names


def test_masking_hides_names_handles_and_speakers_but_keeps_test_tags() -> None:
    masked = mask_names(NOTES + RETRO, names_in(NOTES + RETRO))
    for hidden in ("Alex", "Jane", "@spoe88", "@adoe", "Robin", "Kim", "Lee"):
        assert hidden not in masked
    assert f"* {MASK} Exception requests" in masked
    assert "[Flaking Test] [sig-node]" in masked
    assert "kubernetes/website#59188" in masked
    assert "webinars@cncf.io" in masked  # an organisation's address, not a person's handle
    short = mask_names("Thanks Rob and Robinson", {"Robinson Moe"})
    assert short == f"Thanks {MASK} and {MASK}"  # short form of a listed first name


def test_the_model_sees_only_masked_text() -> None:
    _, client = run([])
    sent = str(client.calls[0])
    assert "Alex" not in sent
    assert "@rmoe" not in sent
    assert MASK in sent


def test_quotes_must_match_word_for_word_and_failures_are_counted() -> None:
    result, _ = run(
        [
            item("action", "We'll start   planning for rc.0 soon,", "Release Branch Management"),
            item("risk", "rc.0 might slip into January", "Release Branch Management"),
            item("issue", "rc.0 soon"),
            item("action", "We'll start planning for rc.0 soon,"),
        ]
    )
    assert [i.quote for i in result.items] == ["We'll start planning for rc.0 soon,"]
    assert result.dropped == {"quote_not_found": 1, "quote_too_short": 1, "duplicate": 1}
    assert result.returned == 4


def test_quote_with_a_name_is_checked_against_the_masked_text() -> None:
    result, _ = run([item("action", "Mid cycle blog: Alex has raised the PR")])
    assert result.items == ()
    result, _ = run([item("action", f"Mid cycle blog: {MASK} has raised the PR")])
    assert len(result.items) == 1


def test_owner_must_be_a_listed_team_never_a_person() -> None:
    quote = "In review the code freeze exception requests with Release Lead."
    result, _ = run([item("action", quote, "Enhancements"), item("risk", quote, "Alex Doe")])
    assert [i.owner for i in result.items] == ["Enhancements", None]
    assert result.unknown_owners == 1


def test_only_explicit_kep_and_pr_references_become_links() -> None:
    assert links_in("KEP-6395 was removed at Code Freeze") == ("kubernetes/enhancements#6395",)
    assert links_in("see https://github.com/kubernetes/kubernetes/pull/143709 now") == (
        "kubernetes/kubernetes#143709",
    )
    assert links_in("Alex has raised the PR (kubernetes/website#59188) for review.") == (
        "kubernetes/website#59188",
    )
    assert links_in("see github.com/kubernetes/enhancements/issues/6395 and KEP-6395") == (
        "kubernetes/enhancements#6395",
    )
    assert links_in("fixed in #59188") == ()  # a bare number names no repo: left to a person


def test_items_are_suggested_and_a_rerun_adds_nothing() -> None:
    result, _ = run([item("issue", "KEP-6395 was removed at Code Freeze and needs an exception.")])
    stored = result.items[0]
    assert (stored.review, stored.raid_id) == ("suggested", None)
    assert stored.links == ("kubernetes/enhancements#6395",)
    store = MemoryRaidStore()
    assert store_all(store, [result], NOW) == 1
    assert store_all(store, [result], NOW) == 0


def test_cost_is_reported_and_the_prompt_file_loads() -> None:
    result, _ = run([])
    assert result.cost_usd > 0
    assert result.items == ()
    assert load_prompt("raid_extractor").label == "raid_extractor.v2"


def test_a_surname_on_its_own_is_masked_too() -> None:
    from modules.raid.mask import MASK, mask_names

    out = mask_names("Thanks to Roe for the docs; KEP-6395 needs a Lead.", {"Jane Roe", "Al Lead"})
    assert out == f"Thanks to {MASK} for the docs; KEP-6395 needs a {MASK}."
