"""The readiness and retro contract's examples are valid API models."""

from __future__ import annotations

import json
import re
from pathlib import Path

from api.readiness_schemas import PatternsOut, ReadinessOut, RetroOut, SaidVsShowedOut

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "api" / "readiness-retro-contract.md"


def test_contract_examples_match_the_models() -> None:
    text = CONTRACT.read_text()
    ex = {m.group(1).strip(): json.loads(m.group(2))
          for m in re.finditer(r"^### (.+?)\n.*?```json\n(.*?)```", text, re.S | re.M)}  # fmt: skip
    ReadinessOut.model_validate(ex["GET /readiness"])
    RetroOut.model_validate(ex["GET /retro"])
    SaidVsShowedOut.model_validate(ex["GET /retro/said-vs-showed"])
    PatternsOut.model_validate(ex["GET /retro/patterns"])
    assert all(v["synthetic"] for v in ex.values())
