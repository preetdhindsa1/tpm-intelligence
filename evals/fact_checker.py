"""Fact-checker suite: does the checker give the labelled verdict for each claim?

Cases live in ``evals/cases/fact_checker.jsonl`` with their facts in ``fact_sets.json``.
``label_status`` is ``proposed`` (written by the developer) until a TPM reviews it, then
``reviewed``. Both are scored, and the split is reported.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from verify.checker import check_claim
from verify.claims import Claim
from verify.facts import Fact, FactKind, FactSheet

CASES = Path(__file__).parent / "cases"
MIN_AGREEMENT = 1.0  # the checker is deterministic: every labelled case must agree


def _fact_value(kind: FactKind, value: Any) -> Any:
    return datetime.fromisoformat(value) if kind is FactKind.DATE and value is not None else value


def load_fact_sets(path: Path = CASES / "fact_sets.json") -> dict[str, FactSheet]:
    """Named fact sheets the cases refer to."""
    raw = json.loads(path.read_text())
    return {
        name: FactSheet(
            Fact(f["key"], FactKind(f["kind"]), _fact_value(FactKind(f["kind"]), f["value"]))
            for f in facts
        )
        for name, facts in raw.items()
    }


def load_cases(path: Path = CASES / "fact_checker.jsonl") -> list[dict[str, Any]]:
    """One dict per non-empty line."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run(cases_dir: Path = CASES) -> dict[str, Any]:
    """Score every case; ``passed`` is agreement >= MIN_AGREEMENT."""
    sets = load_fact_sets(cases_dir / "fact_sets.json")
    cases = load_cases(cases_dir / "fact_checker.jsonl")
    failures: list[dict[str, Any]] = []
    by_reason: Counter[str] = Counter()
    for case in cases:
        claim = Claim.model_validate(case["claim"])
        got = check_claim(claim, sets[case["fact_set"]])
        expected = (case["label"]["verdict"], case["label"]["reason"])
        actual = (got.verdict.value, got.reason.value if got.reason else None)
        by_reason[actual[1] or "verified"] += 1
        if actual != expected:
            failures.append(
                {"id": case["id"], "expected": expected, "actual": actual, "detail": got.detail}
            )
    n = len(cases)
    agreement = (n - len(failures)) / n if n else None
    return {
        "suite": "fact_checker",
        "cases": n,
        "labels": dict(Counter(c.get("label_status", "proposed") for c in cases)),
        "agreement": round(agreement, 4) if agreement is not None else None,
        "threshold": MIN_AGREEMENT,
        "passed": agreement is not None and agreement >= MIN_AGREEMENT,
        "verdicts": dict(sorted(by_reason.items())),
        "failures": failures,
    }
