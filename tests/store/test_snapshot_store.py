"""Forecast snapshots in Postgres: round trip, once a day, and append-only (migration 0007)."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from api.snapshots import FeatureSnapshot, PostgresSnapshotStore, SnapshotRun
from tests.engine.conftest import utc

pytestmark = pytest.mark.integration


def run(version: str = "forecast-m7.1+abc") -> SnapshotRun:
    f = FeatureSnapshot(
        "kubernetes/enhancements#6395",
        True,
        "forecast",
        0.4,
        0.3,
        0.5,
        0.2,
        "forecast",
        None,
        1.0,
        3.5,
        9.0,
        0.3,
        0.8,
        [[0, 0.3, 0.2, 0.4]],
    )
    return SnapshotRun(
        "kubernetes:v1.38",
        utc(2026, 11, 10).date(),
        utc(2026, 11, 10),
        version,
        utc(2026, 11, 17, 12),
        utc(2026, 12, 16),
        {"config": {"durations": "main"}},
        (f,),
    )


def test_round_trip_and_one_run_per_day(engine: Engine) -> None:
    store = PostgresSnapshotStore(sessionmaker(engine))
    v = "forecast-m7.1+roundtrip"
    assert not store.has("kubernetes:v1.38", utc(2026, 11, 10).date(), v)
    rid = store.save(run(v))
    assert rid is not None
    assert store.save(run(v)) is None  # same day and version: never overwritten
    [back] = store.runs("kubernetes:v1.38", v)
    assert back.id == rid
    assert back.features == run(v).features
    assert back.body == run(v).body


def test_stored_snapshots_cannot_be_edited_or_deleted(engine: Engine) -> None:
    store = PostgresSnapshotStore(sessionmaker(engine))
    store.save(run("forecast-m7.1+locked"))
    for sql in (
        "UPDATE forecast_snapshots SET probability = 0.99",
        "DELETE FROM forecast_snapshots",
        "UPDATE forecast_snapshot_runs SET model_version = 'edited'",
        "DELETE FROM forecast_snapshot_runs",
    ):
        with engine.connect() as conn, pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text(sql))
