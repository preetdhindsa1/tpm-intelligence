"""CI gate without paid calls: a passing live run must exist for each agent's current prompt
and default model.

Changing ``agents/prompts/<agent>.v*.md`` or a model default changes the SHA or model, so CI
fails until ``make evals-live`` is run and its results file committed (CLAUDE.md section 8:
any prompt or model change must pass evals before merge).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.gateway import TaskSpec
from agents.prompts import load_prompt
from agents.settings import AISettings

RESULTS = Path(__file__).resolve().parent.parent / "docs" / "results"


def _tasks() -> list[TaskSpec]:
    from agents.risk_analyst import TASK as RISK
    from agents.vp_summary import TASK as VP

    return [RISK, VP]


def check(task: TaskSpec, results_dir: Path = RESULTS) -> dict[str, Any]:
    """Pass if the newest results file for this task, prompt SHA and model passed."""
    prompt = load_prompt(task.name)
    model = AISettings.model_fields[f"model_{task.role.value}"].default
    matching = []
    for path in sorted(results_dir.glob("agent-evals-*.json")):
        data = json.loads(path.read_text())
        if (
            data.get("task", "risk_analyst") == task.name
            and data.get("prompt_sha") == prompt.sha
            and data.get("model") == model
        ):
            matching.append((path.name, data))
    suite = f"agent_gate:{task.name}"
    if not matching:
        return {
            "suite": suite,
            "passed": False,
            "reason": (
                f"no live eval for {prompt.label} ({prompt.sha[:12]}) on {model}: "
                "run make evals-live"
            ),
        }
    name, data = matching[-1]
    return {
        "suite": suite,
        "passed": bool(data.get("passed")),
        "results_file": name,
        "prompt": prompt.label,
        "model": model,
        "summary": data.get("summary"),
    }


def run(results_dir: Path = RESULTS) -> list[dict[str, Any]]:
    """One result per agent."""
    return [check(t, results_dir) for t in _tasks()]
