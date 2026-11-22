"""Forecast validation gate (mirrors CLAUDE.md section 14 for the simulator).

Odds are shown as validated only if the newest backtest file reports recalibrated skill > 0
at every lead time for **every** release it backtested. Otherwise the dashboard labels them
"not validated" and shows the base rate next to them.

Decision 2026-11-22: checking only the newest release was too lenient. The v1.35-v1.38
backtest passed on v1.38 alone (+0.02 to +0.09) while v1.36 and v1.37 failed at some lead
times, and v1.38 was used to choose the model variant (ADR-0005).
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
            "release": r["release"],
            "lead_days": r["lead_days"],
            "skill": r.get("skill"),
            "skill_raw": r.get("skill_raw"),
            "auc": r.get("auc"),
            "n": r.get("n"),
        }
        for r in sorted(results, key=lambda r: (r["release"], -r["lead_days"]))
    ]
    failing = [lead for lead in leads if lead["skill"] is None or lead["skill"] <= 0]
    if not failing:
        reason = "recalibrated odds beat the base rate at every lead time in every release"
    else:
        where = ", ".join(
            f"{str(lead['release']).split(':')[-1]} at {lead['lead_days']} days" for lead in failing
        )
        reason = f"recalibrated odds do not beat the base rate everywhere (fails: {where})"
    return Validation(not failing, reason, files[-1].name, release, leads)


def load_date_validation(results_dir: Path = DEFAULT_DIR) -> Validation:
    """Read the newest ``date-backtest-*.json`` (merge dates; rule in ADR-0005)."""
    files = sorted(results_dir.glob("date-backtest-*.json"))
    if not files:
        return Validation(False, "merge dates have not been backtested yet")
    data = json.loads(files[-1].read_text())
    results = data.get("results", [])
    if not results:
        return Validation(False, "newest merge-date backtest has no results", files[-1].name)
    leads = [
        {
            "release": r["release"],
            "lead_days": r["lead_days"],
            "coverage": r.get("coverage"),
            "skill": r.get("skill"),
            "n": r.get("n"),
            "passes": r.get("passes"),
        }
        for r in sorted(results, key=lambda r: (r["release"], -r["lead_days"]))
    ]
    failing = [lead for lead in leads if not lead["passes"]]
    if not failing:
        reason = "merge-date ranges are calibrated and beat the baseline at every lead time"
    else:
        reason = (
            f"merge-date forecasts fail their backtest in {len(failing)} of {len(leads)} "
            "cases (ADR-0005)"
        )
    release = max(r["release"] for r in results)
    return Validation(not failing, reason, files[-1].name, release, leads)
