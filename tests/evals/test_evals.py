"""Eval harness: the committed cases pass, and the linking suite scores labelled rows."""

from __future__ import annotations

import csv
from pathlib import Path

from evals import fact_checker, linking, run_evals


def test_fact_checker_suite_agrees_with_every_label() -> None:
    result = fact_checker.run()
    assert result["failures"] == []
    assert result["passed"] is True
    assert result["cases"] >= 30
    # Every removal reason is exercised by at least one labelled case.
    assert set(result["verdicts"]) == {
        "verified",
        "wrong_value",
        "text_mismatch",
        "no_supporting_data",
        "type_mismatch",
        "relation_mismatch",
    }


def test_linking_suite_is_tbd_until_labelled(tmp_path: Path) -> None:
    path = tmp_path / "linking.csv"
    assert linking.run(path)["status"] == "TBD (no sample yet)"
    rows = [
        {"status": "verified", "method": "explicit_key", "label": "yes"},
        {"status": "verified", "method": "explicit_key", "label": "no"},
        {"status": "verified", "method": "feature_gate", "label": "yes"},
        {"status": "suggested", "method": "feature_gate", "label": "unsure"},
        {"status": "suggested", "method": "explicit_key", "label": ""},
    ]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["status", "method", "label"])
        writer.writeheader()
        writer.writerows(rows)
    result = linking.run(path)
    assert result["labelled"] == 3
    assert result["by_method"]["verified:explicit_key"] == {"n": 2, "precision": 0.5}
    assert result["verified_precision"] == round(2 / 3, 3)


def test_run_evals_reports_every_suite() -> None:
    names = [r["suite"] for r in run_evals.run_all()]
    assert names == [
        "fact_checker",
        "linking",
        "agent_gate:risk_analyst",
        "agent_gate:vp_summary",
        "agent_gate:link_suggester",
        "agent_gate:raid_extractor",
    ]
