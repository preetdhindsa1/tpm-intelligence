"""GET /portfolio on the #6395 fixture release (ADR-0025, docs/api/ux-v1-contract.md)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from agents.link_store import LinkSuggestion, MemoryLinkSuggestionStore, SuggestionStatus
from agents.updates import UpdateStatus
from api.ai import AIServices
from api.main import create_app
from api.service import InMemoryEventSource, ReleaseService
from api.validation import Validation
from engine.forecast import ForecastConfig
from tests.engine.conftest import fixture_events, utc

PROGRAM_KEYS = {
    "key",
    "project",
    "display_name",
    "release",
    "planning_tool",
    "code_tools",
    "code_freeze_label",
    "has_lab",
    "as_of",
    "dates",
    "stage",
    "scope",
    "bottleneck",
    "next_decision",
}


class _DraftUpdates(AIServices):
    """The newest update of every release is draft 7."""

    def list_updates(self, view: Any) -> list[tuple[Any, bool]]:
        return [(SimpleNamespace(status=UpdateStatus.DRAFT, id=7), False)]


class _BrokenLinks(MemoryLinkSuggestionStore):
    def list(self, release_key: str, status: SuggestionStatus | None = None) -> list[Any]:
        raise RuntimeError("database is down")


def _client(links: MemoryLinkSuggestionStore) -> TestClient:
    service = ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=ForecastConfig(replications=5, sims=100),
        now=lambda: utc(2026, 11, 21, 3),
        validation=lambda: Validation(False, "test: not validated"),
    )
    return TestClient(create_app(service=service, link_store=links, ai=_DraftUpdates()))


def test_portfolio_shape_and_v138_row() -> None:
    store = MemoryLinkSuggestionStore()
    store.save(
        LinkSuggestion(
            release_key="kubernetes:v1.38",
            pull_request_key="kubernetes/kubernetes#143644",
            feature_key="kubernetes/enhancements#6395",
            status=SuggestionStatus.SUGGESTED,
            evidence={"pr_quote": "as discussed in"},
            input_sha="s",
            prompt_version="link_suggester.v1",
            model="claude-haiku-5-5",
            cost_usd=0.0004,
        )
    )
    res = _client(store).get("/portfolio")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {
        "as_of",
        "totals",
        "programs",
        "waiting_on_you",
        "across_programs",
        "coming_next",
        "skipped",
    }
    [row] = body["programs"]
    assert set(row) == PROGRAM_KEYS
    assert row["key"] == "kubernetes:v1.38"
    assert row["stage"]["current"] == "verify"  # 2026-11-21 is after Code Freeze
    assert row["code_freeze_label"] == "Code Freeze"
    assert row["dates"]["code_freeze_at"] == "2026-11-17T12:00:00Z"
    assert row["next_decision"] == {
        "kind": "approve_exec_update",
        "label": "Approve exec update",
        "count": 1,
        "ref": {"update_id": 7},
    }
    assert [i["kind"] for i in body["waiting_on_you"]] == [
        "approve_exec_update",
        "review_link_suggestions",
    ]
    # The fixture holds only v1.38: the other teams are listed, not dropped.
    assert {s["team"] for s in body["skipped"]} == {"kafka", "tpm-intelligence"}
    assert "preetdhindsa1" not in res.text


def test_a_broken_store_is_listed_and_the_page_still_returns() -> None:
    res = _client(_BrokenLinks()).get("/portfolio")
    assert res.status_code == 200
    body = res.json()
    assert {"team": "kubernetes", "reason": "link suggestions could not be read"} in body["skipped"]
    assert body["programs"][0]["key"] == "kubernetes:v1.38"


def _raid_client(raid: Any) -> TestClient:
    service = ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=ForecastConfig(replications=5, sims=100),
        now=lambda: utc(2026, 11, 21, 3),
        validation=lambda: Validation(False, "test: not validated"),
    )
    links = MemoryLinkSuggestionStore()
    return TestClient(create_app(service=service, link_store=links, ai=_DraftUpdates(),
                                 raid_data=raid))  # fmt: skip


def _raid_store(n: int) -> Any:
    from datetime import UTC, datetime

    from api.raid_store import StoreRaid
    from modules.raid.store import MemoryRaidStore, RaidItem, suggestion_key

    now = datetime(2026, 11, 21, tzinfo=UTC)
    store = MemoryRaidStore()
    for i in range(n):
        quote = f"Item {i} needs a decision before the release."
        key = suggestion_key("doc", "2026-11-18", "risk", quote)
        store.suggest(RaidItem(0, key, "kubernetes:v1.38", "K8S", "risk", "A risk", quote,  # type: ignore[arg-type]
                               "doc", "2026-11-18"), now)  # fmt: skip
    return StoreRaid(lambda: store, {}, lambda: now)


def test_raid_items_waiting_are_a_portfolio_decision_and_raid_is_live() -> None:
    body = _raid_client(_raid_store(3)).get("/portfolio").json()
    rows = [i for i in body["waiting_on_you"] if i["kind"] == "review_raid"]
    assert rows == [{"kind": "review_raid", "program_key": "kubernetes:v1.38",
                     "label": "3 RAID items waiting for review · v1.38", "count": 3,
                     "ref": None}]  # fmt: skip
    assert body["totals"]["waiting_on_you"] == len(body["waiting_on_you"])
    status = {m["module"]: m["status"] for m in body["coming_next"]}
    # No database here: readiness and retro use the synthetic fixtures, which never count.
    assert status == {"raid": "live", "readiness": "planned", "retro": "planned"}


def test_the_synthetic_raid_fixture_is_not_live_and_adds_no_row() -> None:
    body = _raid_client(None).get("/portfolio").json()
    assert all(i["kind"] != "review_raid" for i in body["waiting_on_you"])
    assert {m["status"] for m in body["coming_next"]} == {"planned"}


def test_a_broken_raid_store_is_listed_not_hidden() -> None:
    class Broken:
        synthetic = False

        def all_items(self, key: str) -> list[Any]:
            raise RuntimeError("database is down")

    body = _raid_client(Broken()).get("/portfolio").json()
    assert {"team": "kubernetes", "reason": "RAID items could not be read"} in body["skipped"]
    assert body["programs"][0]["key"] == "kubernetes:v1.38"
