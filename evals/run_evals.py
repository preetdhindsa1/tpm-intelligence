"""Run every eval suite, save results, exit non-zero if any suite fails (CLAUDE.md 8).

    python -m evals.run_evals            # all suites
    python -m evals.run_evals --no-save  # print only (CI)

Results go to ``docs/results/evals-<UTC timestamp>.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals import agent_gate, fact_checker, linking

OUT = Path(__file__).resolve().parent.parent / "docs" / "results"


def run_all() -> list[dict[str, Any]]:
    """Results of every suite, in a stable order."""
    return [fact_checker.run(), linking.run(), agent_gate.run()]


def main(argv: list[str] | None = None) -> int:
    """Run, print a summary, optionally save; return the process exit code."""
    parser = argparse.ArgumentParser(prog="run_evals")
    parser.add_argument("--no-save", action="store_true", help="do not write a results file")
    args = parser.parse_args(argv)

    results = run_all()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = {"measured_at": stamp, "suites": results}
    if not args.no_save:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"evals-{stamp}.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))
    failed = [r["suite"] for r in results if not r["passed"]]
    if failed:
        print(f"FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
