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
    assert row["stage"]["current"] == "freeze"  # 2026-11-21 is after Code Freeze
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
