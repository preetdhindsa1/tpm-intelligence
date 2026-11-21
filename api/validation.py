"""Forecast validation gate (mirrors CLAUDE.md section 14 for the simulator).

Odds are shown as validated only if the newest backtest file reports recalibrated skill > 0
at every lead time for its most recent target release. Otherwise the dashboard labels them
"not validated" and shows the base rate next to them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "docs" / "results"


@dataclass(frozen=True)
class Validation:
    """Outcome of the newest backtest."""

    validated: bool
    reason: str
    source_file: str | None = None
    release: str | None = None
    leads: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """For API responses."""
        return {
            "validated": self.validated,
            "reason": self.reason,
            "source_file": self.source_file,
            "release": self.release,
            "leads": self.leads,
        }


def load_validation(results_dir: Path = DEFAULT_DIR) -> Validation:
    """Read the newest ``backtest-*.json`` and decide."""
    files = sorted(results_dir.glob("backtest-*.json"))
    if not files:
        return Validation(False, "no backtest has been run")
    data = json.loads(files[-1].read_text())
    results = data.get("results", [])
    if not results:
        return Validation(False, "newest backtest has no results", files[-1].name)
    release = max(r["release"] for r in results)
    leads = [
        {
            "lead_days": r["lead_days"],
            "skill": r.get("skill"),
            "skill_raw": r.get("skill_raw"),
            "auc": r.get("auc"),
            "n": r.get("n"),
        }
        for r in results
        if r["release"] == release
    ]
    ok = all(lead["skill"] is not None and lead["skill"] > 0 for lead in leads)
    reason = (
        "recalibrated odds beat the base rate at every lead time"
        if ok
        else "recalibrated odds do not beat the base rate at every lead time"
    )
    return Validation(ok, reason, files[-1].name, release, leads)
