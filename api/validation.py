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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.forecast import DEFAULT_FORECAST, ForecastConfig

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


_STAMP = re.compile(r"\d{8}T\d{6}Z")
# Settings that change the model; a backtest only speaks for the model it ran.
# Defaults are what a results file means when it predates the setting.
MODEL_KEYS = {"required_prs": "main", "durations": "all", "non_code_removal": False}


def _matches(path: Path, config: ForecastConfig) -> bool:
    ran = json.loads(path.read_text()).get("config", {})
    return all(ran.get(k, default) == getattr(config, k) for k, default in MODEL_KEYS.items())


def newest_for(pattern: str, results_dir: Path, config: ForecastConfig) -> list[Path]:
    """Files for ``pattern`` that backtested the deployed model, oldest first."""

    def stamp(p: Path) -> str:
        m = _STAMP.search(p.name)
        return m.group(0) if m else ""

    stamped = sorted(results_dir.glob(pattern), key=stamp)
    return [p for p in stamped if _matches(p, config)]


def load_validation(
    results_dir: Path = DEFAULT_DIR, config: ForecastConfig = DEFAULT_FORECAST
) -> Validation:
    """Read the newest ``backtest-*.json`` of the deployed model and decide."""
    files = newest_for("backtest-*.json", results_dir, config)
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


def load_date_validation(
    results_dir: Path = DEFAULT_DIR, config: ForecastConfig = DEFAULT_FORECAST
) -> Validation:
    """Read the newest ``date-backtest-*.json`` of the deployed model (rule in ADR-0005)."""
    files = newest_for("date-backtest-*.json", results_dir, config)
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


def latest_readiness_backtest(results_dir: Path = DEFAULT_DIR) -> dict[str, Any] | None:
    """The newest ``readiness-backtest-*.json`` (#184), with its file name; None if none."""
    files = sorted(results_dir.glob("readiness-backtest-*.json"), key=lambda p: p.name)
    if not files:
        return None
    return {**json.loads(files[-1].read_text()), "file": files[-1].name}


def load_readiness_validation(results_dir: Path = DEFAULT_DIR) -> Validation:
    """Readiness is validated only when its newest backtest passed the ADR-0032 rule."""
    body = latest_readiness_backtest(results_dir)
    if body is None:
        return Validation(False, "Not validated: the readiness backtest has not run (ADR-0032).")
    v = body["verdict"]
    if v["passed"]:
        return Validation(True, f"Validated: the readiness backtest passed ({v['rule']}).",
                          body["file"])  # fmt: skip
    return Validation(False, f"Not validated: the readiness backtest failed: {v['reason']} "
                      f"(ADR-0032).", body["file"])  # fmt: skip
