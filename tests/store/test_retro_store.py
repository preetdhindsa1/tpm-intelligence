"""PostgresRetroStore against a real, migrated database (migration 0012)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.integration

AT = datetime(2026, 11, 26, 9, tzinfo=UTC)
V138 = "kubernetes:v1.38"


def test_retro_runs_round_trip_and_are_append_only(engine: Engine) -> None:
    from modules.retro.facts import DayFacts, FeatureRow, RetroRun, Slip
    from modules.retro.store import PostgresRetroStore

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE retro_runs RESTART IDENTITY"))
    store = PostgresRetroStore(sessionmaker(engine))
    slip = Slip("kubernetes/enhancements#6395", "Dynamic node-local ephemeral volumes",
                "sig/storage", "late_exception", AT, AT, "ci_failing", 21.0)  # fmt: skip
    row = FeatureRow(slip.feature_key, "sig/storage", True, ("ci_failing",))
    first = RetroRun(V138, AT, AT, "retro-1", 2, (slip,), 0, (DayFacts(AT, 2, 1, 0),), (row,))
    store.add(first)
    store.add(RetroRun("kubernetes:v1.37", AT, AT, "retro-1", 0, (), 0, ()))
    assert store.latest(V138) == first
    assert len(store.latest_all()) == 2
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text("DELETE FROM retro_runs"))
