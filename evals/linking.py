"""Linking suite: precision of the deterministic linker on a hand-labelled sample.

``scripts/sample_link_cases.py`` writes ``evals/cases/linking.csv`` from real data. A TPM
fills the ``label`` column: ``yes`` (the PR is work for that feature), ``no``, or
``unsure`` (excluded). Until rows are labelled the result is "TBD (not yet labelled)"; it
never fails the run, because there is nothing to measure yet.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

CASES = Path(__file__).parent / "cases" / "linking.csv"


def run(path: Path = CASES) -> dict[str, Any]:
    """Precision per method and status over labelled rows."""
    if not path.exists():
        return {"suite": "linking", "status": "TBD (no sample yet)", "passed": True}
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    labelled = [r for r in rows if r.get("label", "").strip().lower() in {"yes", "no"}]
    groups: dict[str, list[bool]] = defaultdict(list)
    for r in labelled:
        groups[f"{r['status']}:{r['method']}"].append(r["label"].strip().lower() == "yes")
    precision = {
        g: {"n": len(v), "precision": round(sum(v) / len(v), 3)} for g, v in sorted(groups.items())
    }
    verified = [ok for g, v in groups.items() if g.startswith("verified:") for ok in v]
    return {
        "suite": "linking",
        "rows": len(rows),
        "labelled": len(labelled),
        "status": "measured" if labelled else "TBD (not yet labelled)",
        "verified_precision": round(sum(verified) / len(verified), 3) if verified else None,
        "by_method": precision,
        "passed": True,  # no threshold until a baseline exists (ADR-0008)
    }
