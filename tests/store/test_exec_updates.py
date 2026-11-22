"""PostgresUpdateStore round trip against a real, migrated database (migration 0004)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from agents.updates import ClaimWarning, ExecUpdate, PostgresUpdateStore, UpdateStatus
from verify.claims import Claim
from verify.facts import Fact, FactKind, FactSheet

pytestmark = pytest.mark.integration

FREEZE = datetime(2026, 11, 17, 12, tzinfo=UTC)


def test_add_get_list_save(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE exec_updates"))
    store = PostgresUpdateStore(sessionmaker(engine))
    claim = Claim(
        text="Code Freeze was 17 November.",
        type=FactKind.DATE,
        refs=("release::code_freeze_at",),
        value="2026-11-17",
    )
    update = ExecUpdate(
        release_key="kubernetes:v1.38",
        as_of=FREEZE,
        header={"release": "v1.38"},
        sections={"summary": [claim], "at_risk": [], "removed": [], "asks": []},
        facts=FactSheet([Fact("release::code_freeze_at", FactKind.DATE, FREEZE)]),
        counts={"verified": 1},
        removed=[{"text": "x", "reason": "no_supporting_data", "detail": None}],
        attempts=1,
        model="claude-opus-5-5",
        prompt_version="vp_summary.v1",
        cost_usd=0.1764,
    )
    stored = store.add(update)
    assert stored.id is not None
    got = store.get(stored.id)
    assert got is not None
    assert got.sections["summary"] == [claim]
    assert got.facts["release::code_freeze_at"].value == FREEZE

    decided = replace(
        got,
        status=UpdateStatus.APPROVED,
        decided_by="Harpreet (local, unauthenticated)",
        decided_at=FREEZE,
        warnings=[ClaimWarning("summary", "x", "text_mismatch", None)],
        approved_with_warnings=True,
    )
    store.save(decided)
    again = store.get(stored.id)
    assert again is not None
    assert again.status is UpdateStatus.APPROVED
    assert again.warnings[0].reason == "text_mismatch"
    assert [u.id for u in store.list("kubernetes:v1.38")] == [stored.id]
