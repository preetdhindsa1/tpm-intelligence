"""PostgresSimStore round trip against a real, migrated database (migration 0006)."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from api.sim_store import PostgresSimStore, ScenarioExistsError
from tests.simulator.test_scenario import calibration

pytestmark = pytest.mark.integration


def test_calibration_and_scenarios_round_trip(engine: Engine) -> None:
    store = PostgresSimStore(sessionmaker(engine))
    assert store.latest_calibration("kubernetes:v1.38") is None
    store.save_calibration(calibration(effort=0.3))
    row = store.save_calibration(calibration())
    latest = store.latest_calibration("kubernetes:v1.38")
    assert latest is not None
    assert latest.id == row.id
    assert latest.calibration == calibration()

    saved = store.save_scenario(
        "kubernetes:v1.38", row.id, "hire two", {"pools": {}}, {"total": 1}, "user:test"
    )
    assert saved.created_at is not None
    with pytest.raises(ScenarioExistsError):
        store.save_scenario("kubernetes:v1.38", row.id, "hire two", {}, {}, "user:test")
    assert [s.id for s in store.list_scenarios("kubernetes:v1.38")] == [saved.id]
    assert store.get_scenario("kubernetes:v1.38", saved.id) == saved
    assert store.get_scenario("kubernetes:v1.37", saved.id) is None
