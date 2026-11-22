"""PostgresLedger against a real, migrated database (migration 0002)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from agents.ledger import PostgresLedger, UsageRecord
from agents.pricing import TokenUsage

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)


def test_spend_cache_and_counts(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE ai_usage, ai_results"))
    ledger = PostgresLedger(sessionmaker(engine))
    usage = (TokenUsage("claude-haiku-5-5", input_tokens=10_000, output_tokens=2_000),)

    def rec(fp: str, outcome: str, at: datetime, essential: bool = False) -> UsageRecord:
        paid = usage if outcome == "ok" else ()
        return UsageRecord("smoke", "smoke.v1", "m", essential, outcome, fp, usages=paid, at=at)

    ledger.record(rec("f1", "ok", NOW))
    ledger.record(rec("f0", "ok", NOW - timedelta(days=1)))
    ledger.record(rec("f2", "budget_denied", NOW, essential=True))

    assert ledger.spent_today(NOW) == pytest.approx(0.002)  # yesterday's call excluded
    assert ledger.last_nonessential_at(NOW) == NOW

    assert ledger.get_result("f1") is None
    ledger.put_result("f1", task="smoke", prompt_version="smoke.v1", model="m", output={"a": 1})
    ledger.put_result("f1", task="smoke", prompt_version="smoke.v1", model="m", output={"a": 2})
    ledger.set_check_counts("f1", {"verified": 3})
    cached = ledger.get_result("f1")
    assert cached is not None
    assert cached.output == {"a": 1}  # first write wins
    assert cached.check_counts == {"verified": 3}
