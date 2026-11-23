"""API endpoints on the real #6395 / #2570 fixtures, plus SSE and trace continuity."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from api.live import InMemoryUpdates
from api.main import create_app
from api.service import InMemoryEventSource, ReleaseService
from api.validation import Validation, load_validation
from engine.forecast import ForecastConfig
from pipeline.notify import notification
from tests.engine.conftest import fixture_events, utc

# Results files without a recorded config describe the pre-M7 model (all-PR durations).
OLD = ForecastConfig(durations="all")
FAST = ForecastConfig(replications=5, sims=100)


def client_at(
    now: datetime, updates: InMemoryUpdates | None = None, source: InMemoryEventSource | None = None
) -> TestClient:
    source = source or InMemoryEventSource(list(fixture_events()))
    service = ReleaseService(
        source,
        forecast=FAST,
        now=lambda: now,
        validation=lambda: Validation(False, "test: not validated"),
    )
    return TestClient(create_app(service=service, updates=updates))


@pytest.fixture(scope="module")
def after_readd() -> TestClient:
    return client_at(utc(2026, 11, 21, 3))


def test_releases(after_readd: TestClient) -> None:
    [release] = after_readd.get("/releases").json()
    assert release["name"] == "v1.38"
    assert release["code_freeze_at"] == "2026-11-17T12:00:00Z"
    assert release["features_ever_in_release"] == 2


def test_feature_table_row_for_6395(after_readd: TestClient) -> None:
    body = after_readd.get("/releases/v1.38/features").json()
    row = next(f for f in body["features"] if f["number"] == 6395)
    assert row["in_release"] is True
    assert row["tracked"] is True
    assert (row["prs_total"], row["prs_merged"], row["suggested_prs"]) == (5, 4, 1)
    codes = {f["code"] for f in row["flags"]}
    assert {"removed_at_freeze", "readded_after_freeze", "merged_after_freeze"} <= codes
    assert row["odds"]["status"] == "after_freeze"
    assert "calibration" in body


def test_feature_detail_for_6395(after_readd: TestClient) -> None:
    d = after_readd.get("/releases/v1.38/features/6395").json()
    main = [p for p in d["pull_requests"] if p["is_main"]]
    assert [p["key"] for p in main] == ["kubernetes/kubernetes#143709"]
    assert main[0]["freeze_status"] == "merged_after_freeze_with_exception"
    assert main[0]["counts_for_release"] is True
    assert main[0]["url"] == "https://github.com/kubernetes/kubernetes/pull/143709"
    kinds = [e["kind"] for e in d["timeline"]]
    assert kinds.index("code_freeze") < kinds.index("removed_from_release")
    assert d["suggested_pull_requests"] == ["kubernetes/kubernetes#143644"]
    assert "Not a guarantee" in d["assumptions"]["note"]


def test_removed_feature_can_be_hidden(after_readd: TestClient) -> None:
    on_nov_18 = client_at(utc(2026, 11, 18))
    all_rows = on_nov_18.get("/releases/v1.38/features").json()["features"]
    current = on_nov_18.get("/releases/v1.38/features?include_removed=false").json()["features"]
    assert {r["number"] for r in all_rows} == {6395, 2570}
    assert current == []  # both were removed at Code Freeze on Nov 17


def test_odds_before_freeze_have_a_range() -> None:
    row = next(
        f
        for f in client_at(utc(2026, 11, 10)).get("/releases/v1.38/features").json()["features"]
        if f["number"] == 6395
    )
    odds = row["odds"]
    assert odds["status"] == "forecast"
    assert 0.0 <= odds["low"] <= odds["probability"] <= odds["high"] <= 1.0
    assert "kubernetes/kubernetes#143709" in odds["open_prs"]


def test_unlinked_load_is_per_sig(after_readd: TestClient) -> None:
    body = after_readd.get("/releases/v1.38/load").json()
    assert all(set(row) == {"sig", "open_unlinked_prs"} for row in body["by_sig"])


@pytest.mark.parametrize("path", ["/releases/v9.99/features", "/releases/v1.38/features/1"])
def test_not_found(after_readd: TestClient, path: str) -> None:
    assert after_readd.get(path).status_code == 404


def test_sse_pushes_update_inside_the_workers_trace(spans: InMemorySpanExporter) -> None:
    events = list(fixture_events())
    source = InMemoryEventSource(events[:-1])  # hold back one event
    updates = InMemoryUpdates(heartbeat_s=0.05)
    client = client_at(utc(2026, 11, 21, 3), updates, source)

    received: list[str] = []
    with client.stream("GET", "/releases/v1.38/stream") as response:
        lines = response.iter_lines()
        assert next(lines) == "event: ready"

        def worker_stores_event() -> str:
            # Simulate the worker: store the event, then notify inside its own span.
            with trace.get_tracer("test").start_as_current_span("worker.store") as span:
                source.events.append(events[-1])
                updates.publish(notification(events[-1].event_id, "x"))
                return format(span.get_span_context().trace_id, "032x")

        trace_id: list[str] = []
        threading.Timer(0.1, lambda: trace_id.append(worker_stores_event())).start()
        for line in lines:
            received.append(line)
            if line == "event: update":
                received.append(next(lines))
                break

    data = json.loads(received[-1].removeprefix("data: "))
    assert data["release"] == "v1.38"
    push = [s for s in spans.get_finished_spans() if s.name == "api.push_update"]
    assert push
    assert format(push[0].context.trace_id, "032x") == trace_id[0]


def test_odds_are_labelled_not_validated() -> None:
    body = client_at(utc(2026, 11, 10)).get("/releases/v1.38/features").json()
    assert body["validation"]["validated"] is False
    row = next(f for f in body["features"] if f["number"] == 6395)
    assert row["odds"]["validated"] is False
    assert row["odds"]["base_rate"] is not None
    assert row["odds"]["raw_probability"] is not None


def test_validation_gate_reads_newest_backtest(tmp_path: Path) -> None:
    import json

    def write(name: str, skills: list[float]) -> None:
        results = [
            {
                "release": "kubernetes:v1.38",
                "lead_days": lead,
                "skill": s,
                "skill_raw": s,
                "auc": 0.7,
                "n": 80,
            }
            for lead, s in zip((28, 14, 7), skills, strict=True)
        ]
        (tmp_path / name).write_text(json.dumps({"results": results}))

    assert load_validation(tmp_path, OLD).validated is False  # nothing run yet
    write("backtest-20261101T000000Z.json", [0.1, 0.2, 0.05])
    assert load_validation(tmp_path, OLD).validated is True
    write("backtest-20261121T000000Z.json", [0.1, -0.02, 0.05])  # newest wins
    v = load_validation(tmp_path, OLD)
    assert v.validated is False
    assert v.source_file == "backtest-20261121T000000Z.json"


def test_validation_gate_requires_every_backtested_release(tmp_path: Path) -> None:
    """Shape of the 2026-11-22 backtest: newest release passes, an earlier one fails."""
    import json

    skills = {
        "kubernetes:v1.36": (0.085, -0.154, -0.285),
        "kubernetes:v1.37": (0.127, 0.07, -0.013),
        "kubernetes:v1.38": (0.086, 0.02, 0.035),
    }
    results = [
        {"release": rel, "lead_days": lead, "skill": s, "skill_raw": -0.5, "auc": 0.6, "n": 80}
        for rel, row in skills.items()
        for lead, s in zip((28, 14, 7), row, strict=True)
    ]
    (tmp_path / "backtest-20261122T000000Z.json").write_text(json.dumps({"results": results}))
    v = load_validation(tmp_path, OLD)
    assert v.validated is False
    assert v.release == "kubernetes:v1.38"
    assert "v1.36 at 14 days" in v.reason
    assert "v1.37 at 7 days" in v.reason
    assert "v1.38" not in v.reason
    assert len(v.leads) == 9


def test_risk_note_endpoint_returns_only_verified_claims() -> None:
    from agents.gateway import Gateway
    from agents.ledger import MemoryLedger
    from agents.notes import MemoryNoteStore
    from agents.settings import AISettings
    from api.ai import AIServices
    from tests.agents.test_risk_analyst import BAD, Sequenced

    client = Sequenced(BAD, BAD)
    service = ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=FAST,
        now=lambda: utc(2026, 11, 10),
        validation=lambda: Validation(False, "test: not validated"),
    )
    ai = AIServices(gateway=Gateway(AISettings(), MemoryLedger(), client), notes=MemoryNoteStore())
    api = TestClient(create_app(service=service, ai=ai))
    body = api.get("/releases/v1.38/features/6395/risk-note").json()
    assert body["status"] == "fresh"
    assert body["attempts"] == 2
    assert [c["text"] for c in body["claims"]] == [BAD.claims[0 + 2].text]
    assert body["claims_removed"] == 2
    assert body["removed_by_reason"] == {"no_supporting_data": 1, "wrong_value": 1}
    assert body["odds_validated"] is False
    again = api.get("/releases/v1.38/features/6395/risk-note").json()
    assert again["status"] == "reused"
    assert len(client.calls) == 2
    assert api.get("/releases/v1.38/features/9999/risk-note").status_code == 404


def test_update_endpoints_draft_edit_approve() -> None:
    from agents.gateway import Gateway
    from agents.ledger import MemoryLedger
    from agents.notes import MemoryNoteStore
    from agents.settings import AISettings
    from agents.updates import MemoryUpdateStore
    from api.ai import AIServices
    from tests.agents.test_gateway import FakeClient, Response
    from tests.agents.test_vp_summary import OUTPUT

    service = ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=FAST,
        now=lambda: utc(2026, 11, 21, 3),
        validation=lambda: Validation(False, "test: not validated"),
    )
    client = FakeClient(Response(parsed_output=OUTPUT, model="claude-opus-5-5"))
    ai = AIServices(
        gateway=Gateway(AISettings(), MemoryLedger(), client),
        notes=MemoryNoteStore(),
        updates=MemoryUpdateStore(),
    )
    api = TestClient(create_app(service=service, ai=ai))

    created = api.post("/releases/v1.38/updates")
    assert created.status_code == 201
    body = created.json()
    uid = body["id"]
    assert body["status"] == "draft"
    assert body["stale"] is False
    assert body["claims_removed"] == 1
    assert "Reallocating" not in body["markdown"]

    sections = {"summary": body["sections"]["summary"], "asks": body["sections"]["asks"]}
    edited = api.patch(f"/releases/v1.38/updates/{uid}", json={"sections": sections}).json()
    assert edited["edited"] is True
    assert edited["warnings"] == []
    assert edited["sections"]["at_risk"] == []

    approved = api.post(f"/releases/v1.38/updates/{uid}/approve", json={}).json()
    assert approved["status"] == "approved"
    assert approved["decided_by"] == "user:local (local, unauthenticated)"
    again = api.post(f"/releases/v1.38/updates/{uid}/approve", json={})
    assert again.status_code == 409
    assert [u["id"] for u in api.get("/releases/v1.38/updates").json()] == [uid]
    assert api.get("/releases/v1.38/updates/999").status_code == 404


def test_link_review_queue_confirm_changes_the_facts() -> None:
    from agents.link_store import (
        LinkSuggestion,
        MemoryLinkSuggestionStore,
        SuggestionStatus,
        engine_links,
    )
    from api.ai import AIServices

    store = MemoryLinkSuggestionStore()
    for pr, status in (
        ("kubernetes/kubernetes#143644", SuggestionStatus.SUGGESTED),
        ("kubernetes/kubernetes#143442", SuggestionStatus.DROPPED),
    ):
        store.save(
            LinkSuggestion(
                release_key="kubernetes:v1.38",
                pull_request_key=pr,
                feature_key="kubernetes/enhancements#6395",
                status=status,
                evidence={"pr_quote": "as discussed in", "feature_quote": "ephemeral volumes"},
                input_sha="s",
                prompt_version="link_suggester.v1",
                model="claude-haiku-5-5",
                cost_usd=0.0004,
            )
        )
    service = ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=FAST,
        now=lambda: utc(2026, 11, 21, 3),
        validation=lambda: Validation(False, "test: not validated"),
        extra_links=lambda key: engine_links(store.list(key)),
    )
    client = TestClient(create_app(service=service, link_store=store, ai=AIServices()))

    def row_6395() -> dict[str, int]:
        rows = client.get("/releases/v1.38/features").json()["features"]
        return next(f for f in rows if f["number"] == 6395)

    queue = client.get("/releases/v1.38/link-suggestions").json()
    assert queue["counts"] == {"suggested": 1, "dropped": 1}
    (item,) = queue["suggestions"]  # dropped answers are never shown as links
    assert item["pull_request_title"]
    assert item["feature_number"] == 6395
    assert (row_6395()["prs_total"], row_6395()["suggested_prs"]) == (5, 1)

    done = client.post(f"/releases/v1.38/link-suggestions/{item['id']}/confirm", json={})
    assert done.status_code == 200
    assert done.json()["decided_by"] == "user:local (local, unauthenticated)"
    assert (row_6395()["prs_total"], row_6395()["suggested_prs"]) == (6, 0)

    again = client.post(f"/releases/v1.38/link-suggestions/{item['id']}/reject", json={})
    assert again.status_code == 409
    assert client.post("/releases/v1.38/link-suggestions/99/confirm", json={}).status_code == 404
    assert client.get("/releases/v1.38/link-suggestions?status=bogus").status_code == 422


def test_simulator_endpoints_label_not_validated_and_save_scenarios() -> None:
    from api.ai import AIServices
    from api.sim_store import MemorySimStore
    from tests.simulator.test_scenario import calibration

    store = MemorySimStore()
    service = ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=FAST,
        now=lambda: utc(2026, 11, 3),
        validation=lambda: Validation(False, "test: not validated"),
    )
    client = TestClient(create_app(service=service, sim_store=store, ai=AIServices()))
    assert client.get("/releases/v1.38/simulator").status_code == 404  # not calibrated yet
    store.save_calibration(calibration())

    info = client.get("/releases/v1.38/simulator").json()
    assert info["validated"] is False
    assert "not validated" in info["note"]
    assert info["horizon_label"] == "Code Freeze"
    assert info["source_releases"] == ["kubernetes:v1.37"]
    assert {p["pool"] for p in info["pools"]} == {"sig/node", "other"}

    body = {"name": "cut node", "pools": {"sig/node": {"reviewers": -1}}}
    sim = client.post("/releases/v1.38/simulate", json=body).json()
    assert sim["validated"] is False
    assert "not validated" in sim["note"]
    assert sim["baseline"]["total"]["merged"]["low"] <= sim["baseline"]["total"]["merged"]["high"]
    node = next(p for p in sim["scenario"]["pools"] if p["pool"] == "sig/node")
    now = next(p for p in info["pools"] if p["pool"] == "sig/node")["reviewers_now"]
    assert node["reviewers"] == max(0, now - 1)

    bad = client.post("/releases/v1.38/simulate", json={"pools": {"sig/nope": {}}})
    assert bad.status_code == 422
    assert client.post("/releases/v1.38/scenarios", json={"pools": {}}).status_code == 422

    saved = client.post("/releases/v1.38/scenarios", json=body)
    assert saved.status_code == 201
    row = saved.json()
    assert row["created_by"] == "user:local (local, unauthenticated)"
    assert row["result"]["scenario"] == sim["scenario"]  # same seeds, same result
    assert client.post("/releases/v1.38/scenarios", json=body).status_code == 409
    assert [s["id"] for s in client.get("/releases/v1.38/scenarios").json()] == [row["id"]]
    assert client.get(f"/releases/v1.38/scenarios/{row['id']}").json()["name"] == "cut node"
    assert client.get("/releases/v1.38/scenarios/999").status_code == 404


def test_summary_outcomes_on_the_6395_fixtures(after_readd: TestClient) -> None:
    s = after_readd.get("/releases/v1.38/summary").json()
    assert s["phase"] == "after_freeze"
    by_key = {f["key"]: f["outcome"] for f in s["features"]}
    # Removed at Code Freeze Nov 17, re-added Nov 21: not landed, back by exception.
    assert by_key["kubernetes/enhancements#6395"] == "readded_after_freeze"
    assert by_key["kubernetes/enhancements#2570"] == "readded_after_freeze"
    assert sum(s["outcomes"].values()) == s["features_ever"] == len(s["features"])
    # The tile and the chart agree: every removal at freeze is either still out or re-added.
    flagged = {
        f["key"]
        for f in after_readd.get("/releases/v1.38/features").json()["features"]
        if any(x["code"] == "removed_at_freeze" for x in f["flags"])
    }
    assert len(flagged) == s["removed_at_freeze"]
    assert {by_key[k] for k in flagged} <= {"removed_at_freeze", "readded_after_freeze"}


def test_summary_is_too_early_before_the_outcome_is_known() -> None:
    s = client_at(utc(2026, 11, 3)).get("/releases/v1.38/summary").json()
    assert s["phase"] == "before_freeze"
    assert s["landed"] is None
    assert set(s["outcomes"]) == {"too_early"}


def test_graph_has_verified_links_only(after_readd: TestClient) -> None:
    g = after_readd.get("/releases/v1.38/graph").json()
    nodes = {n["id"]: n for n in g["nodes"]}
    edges = {(e["source"], e["target"], e["kind"]) for e in g["edges"]}
    f = "kubernetes/enhancements#6395"
    assert nodes[f]["kind"] == "feature"
    assert ("kubernetes:v1.38", f, "contains") in edges
    main = "kubernetes/kubernetes#143709"
    assert (f, main, "implemented_by") in edges
    assert nodes[main]["state"] == "merged"
    # #143644 only mentions #6395 in passing: a suggestion, never a graph edge.
    assert (f, "kubernetes/kubernetes#143644", "implemented_by") not in edges
    assert all(e["source"] in nodes and e["target"] in nodes for e in g["edges"])


def test_dependencies_page_data_on_the_6395_fixtures(after_readd: TestClient) -> None:
    d = after_readd.get("/releases/v1.38/dependencies").json()
    keys = {f["key"] for f in d["features"]}
    assert "kubernetes/enhancements#6395" in keys
    f = next(x for x in d["features"] if x["key"] == "kubernetes/enhancements#6395")
    assert f["outcome"] == "readded_after_freeze"
    prs = {p["number"] for p in f["prs"]}
    assert 143709 in prs
    # #143644 only mentions #6395 in passing: never a verified PR of the feature.
    assert 143644 not in prs
    # Every coupling and cluster refers to listed features; stand-alone ones have none.
    for c in d["couplings"]:
        assert {c["a"], c["b"]} <= keys
    for f in d["features"]:
        assert (f["cluster"] is None) == all(f["key"] not in c for c in d["clusters"])
    assert all(e["kind"] == "blocks" for e in d["pr_edges"])


def test_merge_dates_for_6395_after_its_main_pr_merged(after_readd: TestClient) -> None:
    d = after_readd.get("/releases/v1.38/merge-dates").json()
    item = next(i for i in d["items"] if i["number"] == 6395)
    # #143709 merged Nov 20 23:28 UTC: 3.48 days after Code Freeze.
    assert item["status"] == "done"
    assert abs(item["done_day"] - 3.48) < 0.01
    assert d["done_now"] >= 1
    assert d["validation"]["validated"] in (True, False)
    assert "not a guarantee" in d["note"]
    days = [row[0] for row in d["forecast"]]
    assert days == sorted(days)
    detail = after_readd.get("/releases/v1.38/features/6395").json()
    assert detail["merge_date"]["status"] == "done"


def test_merge_date_validation_reads_the_newest_date_backtest(tmp_path: Path) -> None:
    from api.validation import load_date_validation

    assert not load_date_validation(tmp_path, OLD).validated
    rows = [
        {
            "release": "kubernetes:v1.36",
            "lead_days": 7,
            "coverage": 0.69,
            "skill": -0.5,
            "passes": False,
        },
        {
            "release": "kubernetes:v1.37",
            "lead_days": -3,
            "coverage": 0.82,
            "skill": 0.25,
            "passes": True,
        },
    ]
    (tmp_path / "date-backtest-20261122T000000Z.json").write_text(json.dumps({"results": rows}))
    v = load_date_validation(tmp_path, OLD)
    assert not v.validated
    assert v.reason == "merge-date forecasts fail their backtest in 1 of 2 cases (ADR-0005)"


def test_validation_only_counts_backtests_of_the_deployed_model(tmp_path: Path) -> None:
    from api.validation import load_validation

    def write(name: str, skill: float, **config: object) -> None:
        rows = [{"release": "kubernetes:v1.37", "lead_days": 7, "skill": skill}]
        (tmp_path / name).write_text(json.dumps({"config": config, "results": rows}))

    write("backtest-20261122T010000Z.json", -0.1, required_prs="main")
    write("backtest-20261122T020000Z-B.json", 0.2, required_prs="main", durations="main")
    # The deployed model uses main-PR durations: only the B file speaks for it.
    assert load_validation(tmp_path).validated
    assert not load_validation(tmp_path, ForecastConfig(durations="all")).validated


def test_in_memory_updates_accept_publishes_from_another_thread() -> None:
    """The in-process worker publishes from its own thread (ADR-0017)."""
    import asyncio

    updates = InMemoryUpdates(heartbeat_s=5)

    async def scenario() -> object:
        async def never() -> bool:
            return False

        stream = updates.subscribe(never)
        first = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0.05)  # subscribed
        threading.Thread(target=updates.publish, args=(notification("e1", "x"),)).start()
        return await asyncio.wait_for(first, timeout=2)

    assert asyncio.run(scenario()) is not None  # a trace context, not a heartbeat


def test_sse_stream_ends_after_its_maximum_so_browsers_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.main as main_mod

    monkeypatch.setattr(main_mod, "STREAM_MAX_S", 0.2)
    updates = InMemoryUpdates(heartbeat_s=0.05)
    client = client_at(utc(2026, 11, 21, 3), updates, InMemoryEventSource(list(fixture_events())))
    started = time.monotonic()
    with client.stream("GET", "/releases/v1.38/stream") as response:
        lines = list(response.iter_lines())  # returns only because the server ends it
    assert time.monotonic() - started < 5
    assert lines[0] == "event: ready"
    assert "retry: 1000" in lines
