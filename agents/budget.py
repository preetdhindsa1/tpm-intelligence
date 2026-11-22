"""Daily AI budget policy (CLAUDE.md section 8). Pure, no I/O.

* Below ``slow_at`` (80%) of the cap: every call may run.
* From 80%: non-essential calls are slowed to one per ``slow_interval_s``.
* At 100%: non-essential calls pause until the next UTC day. Essential calls (a TPM asked
  for them, e.g. drafting the executive update) may run up to ``essential_overage`` above
  the cap; the default overage is 0, so the cap is hard.

Every check uses the worst-case cost of the call about to run, so a single call cannot
jump far past the cap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BudgetState(StrEnum):
    """Where today's spend sits."""

    NORMAL = "normal"
    SLOW = "slow"
    PAUSED = "paused"


@dataclass(frozen=True)
class BudgetDecision:
    """Whether a call may run now."""

    allowed: bool
    state: BudgetState
    reason: str
    retry_after_s: float | None = None


def budget_state(spent: float, cap: float, slow_at: float) -> BudgetState:
    """State from spend alone."""
    if spent >= cap:
        return BudgetState.PAUSED
    return BudgetState.SLOW if spent >= slow_at * cap else BudgetState.NORMAL


def decide(
    *,
    spent: float,
    estimate: float,
    cap: float,
    essential: bool,
    now: datetime,
    last_nonessential_at: datetime | None,
    slow_at: float = 0.8,
    slow_interval_s: float = 60.0,
    essential_overage: float = 0.0,
) -> BudgetDecision:
    """Decide for one call (see module docstring)."""
    state = budget_state(spent, cap, slow_at)
    if essential:
        limit = cap * (1 + essential_overage)
        if spent + estimate > limit:
            return BudgetDecision(
                False, state, f"essential call would exceed ${limit:.2f} (spent ${spent:.4f})"
            )
        return BudgetDecision(True, state, "essential")
    if state is BudgetState.PAUSED or spent + estimate > cap:
        return BudgetDecision(
            False, BudgetState.PAUSED, f"daily cap ${cap:.2f} reached (spent ${spent:.4f})"
        )
    if state is BudgetState.SLOW and last_nonessential_at is not None:
        waited = (now - last_nonessential_at).total_seconds()
        if waited < slow_interval_s:
            return BudgetDecision(
                False, state, "over 80% of the daily cap: slowed", slow_interval_s - waited
            )
    return BudgetDecision(True, state, "within budget")
