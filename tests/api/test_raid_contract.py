"""The RAID contract's JSON examples are valid API models (docs/api/raid-contract.md)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from api.raid_schemas import RaidHistoryOut, RaidItemOut, RaidListOut, RaidSummaryOut

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "api" / "raid-contract.md"


def _examples() -> dict[str, Any]:
    """Example JSON blocks in the contract, keyed by the heading above each."""
    text = CONTRACT.read_text()
    out: dict[str, Any] = {}
    for m in re.finditer(r"^### (.+?)\n.*?```json\n(.*?)```", text, re.S | re.M):
        out[m.group(1).strip()] = json.loads(m.group(2))
    return out


def test_contract_examples_match_the_models() -> None:
    ex = _examples()
    RaidListOut.model_validate(ex["GET /raid"])
    RaidListOut.model_validate(ex["GET /raid/queue"])
    RaidSummaryOut.model_validate(ex["GET /raid/summary"])
    RaidHistoryOut.model_validate(ex["GET /raid/{item_id}/history"])
    item = RaidItemOut.model_validate(ex["POST /raid/{item_id}/confirm"])
    assert item.raid_id == "K8S-R-002"


def test_examples_are_labelled_synthetic() -> None:
    assert all(v["synthetic"] for v in _examples().values() if "synthetic" in v)
