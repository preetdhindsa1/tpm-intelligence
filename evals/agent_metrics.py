"""Deterministic scores for one agent output (pure, no AI judging AI)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from verify.checker import CheckReport
from verify.facts import FactSheet

_ODDS_VALUES = ("::odds.probability", "::odds.low", "::odds.high")


def critical_coverage(report: CheckReport, critical_keys: Sequence[str]) -> float | None:
    """Share of critical flags cited by a verified claim, directly or via a sub-fact."""
    if not critical_keys:
        return None
    cited = {r for c in report.verified for r in c.refs}
    covered = [k for k in critical_keys if any(r == k or r.startswith(k + ".") for r in cited)]
    return len(covered) / len(critical_keys)


def odds_honest(report: CheckReport, facts: FactSheet) -> bool:
    """Every verified claim that cites odds also cites ``odds.validated`` when it is false."""
    for claim in report.verified:
        odds_refs = [r for r in claim.refs if r.endswith(_ODDS_VALUES)]
        if not odds_refs:
            continue
        validated_key = odds_refs[0].rsplit("::", 1)[0] + "::odds.validated"
        fact = facts.get(validated_key)
        if fact is not None and fact.value is False and validated_key not in claim.refs:
            return False
    return True


def score_case(
    first: CheckReport, best: CheckReport, facts: FactSheet, critical_keys: Sequence[str]
) -> dict[str, Any]:
    """Per-case scores; the gate thresholds live in evals/agents.py."""
    total = len(best.checked)
    return {
        "claims_shown": len(best.verified),
        "removal_rate_first_attempt": first.removal_rate,
        "removal_rate_shown_attempt": best.removal_rate,
        "removed_by_reason": {k: v for k, v in best.counts.items() if k != "verified" and v},
        "critical_coverage": critical_coverage(best, critical_keys),
        "odds_honest": odds_honest(best, facts),
        "claims_total": total,
    }
