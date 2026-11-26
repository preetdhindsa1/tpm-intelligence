"""PostgresDecisionLog against a real, migrated database (migration 0011)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from modules.readiness.decisions import Decision, PostgresDecisionLog

pytestmark = pytest.mark.integration

AT = datetime(2026, 11, 26, 9, tzinfo=UTC)
V138 = "kubernetes:v1.38"


@pytest.fixture
def log(engine: Engine) -> PostgresDecisionLog:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE readiness_decisions RESTART IDENTITY"))
    return PostgresDecisionLog(sessionmaker(engine))


def test_decisions_are_appended_in_order_per_release(log: PostgresDecisionLog) -> None:
    log.append(Decision(V138, "no_go", "Two main PRs open.", AT, AT, "not_ready", "octo"))
    log.append(Decision(V138, "go", "Exceptions approved.", AT, AT, "unknown", "octo"))
    log.append(Decision("kubernetes:v1.37", "go", "Shipped.", AT, AT, "ready", "octo"))
    rows = log.list(V138)
    assert [(d.decision, d.verdict) for d in rows] == [("no_go", "not_ready"), ("go", "unknown")]
    assert rows[0].facts_as_of == AT


@pytest.mark.parametrize("sql", ["UPDATE readiness_decisions SET note = 'changed'",
                                 "DELETE FROM readiness_decisions"])  # fmt: skip
def test_the_database_refuses_changes(log: PostgresDecisionLog, engine: Engine, sql: str) -> None:
    log.append(Decision(V138, "defer", "Wait for CI.", AT, AT, "not_ready", "octo"))
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text(sql))
    assert len(log.list(V138)) == 1
