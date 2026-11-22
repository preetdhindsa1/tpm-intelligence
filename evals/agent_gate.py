"""CI gate without paid calls: a passing live run must exist for the current prompt + model.

Changing ``agents/prompts/risk_analyst.v*.md`` or ``AI_MODEL_SIMPLE``'s default changes the
SHA or model, so CI fails until ``make evals-live`` is run and its results file committed
(CLAUDE.md section 8: any prompt or model change must pass evals before merge).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.prompts import load_prompt
from agents.risk_analyst import TASK
from agents.settings import AISettings

RESULTS = Path(__file__).resolve().parent.parent / "docs" / "results"


def run(results_dir: Path = RESULTS) -> dict[str, Any]:
    """Pass if the newest matching agent-evals file passed."""
    prompt = load_prompt("risk_analyst")
    model = AISettings.model_fields[f"model_{TASK.role.value}"].default
    matching = []
    for path in sorted(results_dir.glob("agent-evals-*.json")):
        data = json.loads(path.read_text())
        if data.get("prompt_sha") == prompt.sha and data.get("model") == model:
            matching.append((path.name, data))
    if not matching:
        return {
            "suite": "agent_gate:risk_analyst",
            "passed": False,
            "reason": (
                f"no live eval for {prompt.label} ({prompt.sha[:12]}) on {model}: "
                "run make evals-live"
            ),
        }
    name, data = matching[-1]
    return {
        "suite": "agent_gate:risk_analyst",
        "passed": bool(data.get("passed")),
        "results_file": name,
        "prompt": prompt.label,
        "model": model,
        "summary": data.get("summary"),
    }
