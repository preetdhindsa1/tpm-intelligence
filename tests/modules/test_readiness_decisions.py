"""The in-memory decision log and the rules every log shares (ADR-0032)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from modules.readiness.decisions import Decision, MemoryDecisionLog

AT = datetime(2026, 11, 26, 9, tzinfo=UTC)


def test_append_and_list_per_release() -> None:
    log = MemoryDecisionLog()
    log.append(Decision("kubernetes:v1.38", "no_go", "CI red.", AT, AT, "not_ready", "octo"))
    log.append(Decision("kubernetes:v1.37", "go", "Shipped.", AT, AT, "ready", "octo"))
    assert [d.note for d in log.list("kubernetes:v1.38")] == ["CI red."]


@pytest.mark.parametrize(("decision", "note"), [("ship", "fine"), ("go", "  ")])
def test_a_bad_decision_or_missing_note_is_refused(decision: str, note: str) -> None:
    with pytest.raises(ValueError, match=r"decision|note"):
        Decision("kubernetes:v1.38", decision, note, AT, AT, "ready", "octo")  # type: ignore[arg-type]
