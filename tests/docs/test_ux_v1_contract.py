"""The contract example (docs/api/ux-v1-contract.md) must follow its own rules (ADR-0025)."""

from __future__ import annotations

import json
import re
from pathlib import Path

CONTRACT = Path(__file__).parents[2] / "docs" / "api" / "ux-v1-contract.md"


def _example() -> dict[str, object]:
    block = re.search(r"```json\n(.*?)```", CONTRACT.read_text(), re.S)
    assert block is not None
    data: dict[str, object] = json.loads(block[1])
    return data


def test_programs_are_in_release_date_order() -> None:
    programs = _example()["programs"]
    assert isinstance(programs, list)
    order = [(p["dates"]["release_at"], p["key"]) for p in programs]
    assert order == sorted(order)


def test_waiting_items_name_their_program_and_decisions_do_not() -> None:
    body = _example()
    keys = {p["key"] for p in body["programs"]}  # type: ignore[attr-defined]
    for item in body["waiting_on_you"]:  # type: ignore[attr-defined]
        assert item["program_key"] in keys
    for p in body["programs"]:  # type: ignore[attr-defined]
        assert p["next_decision"] is None or "program_key" not in p["next_decision"]
