"""API endpoints on the real #6395 / #2570 fixtures, plus SSE and trace continuity."""

from __future__ import annotations

import json
import threading
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

    assert load_validation(tmp_path).validated is False  # nothing run yet
    write("backtest-20261101T000000Z.json", [0.1, 0.2, 0.05])
    assert load_validation(tmp_path).validated is True
    write("backtest-20261121T000000Z.json", [0.1, -0.02, 0.05])  # newest wins
    v = load_validation(tmp_path)
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
    v = load_validation(tmp_path)
    assert v.validated is False
    assert v.release == "kubernetes:v1.38"
    assert "v1.36 at 14 days" in v.reason
    assert "v1.37 at 7 days" in v.reason
    assert "v1.38" not in v.reason
    assert len(v.leads) == 9
