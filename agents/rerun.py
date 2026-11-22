"""Run AI only when facts change meaningfully (CLAUDE.md section 8). Pure, no I/O.

A feature's explanation is regenerated when, since the last run:
* its odds moved by at least ``odds_change_points`` percentage points, or
* any non-odds fact changed (a flag appeared or cleared, a PR merged, removal/re-add,
  stage, validation status).

Small odds jitter from re-simulation never triggers a paid call on its own.
"""

from __future__ import annotations

from collections.abc import Mapping

from verify.facts import Fact, FactKind

_ODDS_FIELDS = ("::odds.probability", "::odds.low", "::odds.high", "::odds.base_rate")


def changed_meaningfully(
    previous: Mapping[str, Fact] | None,
    current: Mapping[str, Fact],
    *,
    odds_change_points: float = 10.0,
) -> tuple[bool, str]:
    """(re-run?, why)."""
    if previous is None:
        return True, "no previous run"
    for key in sorted(set(previous) | set(current)):
        before, after = previous.get(key), current.get(key)
        if before is None or after is None:
            return True, f"fact {'added' if before is None else 'removed'}: {key}"
        if key.endswith(_ODDS_FIELDS) and after.kind is FactKind.PROBABILITY:
            if key.endswith("::odds.probability"):
                b, a = before.value, after.value
                if (
                    isinstance(b, int | float)
                    and isinstance(a, int | float)
                    and abs(a - b) * 100 >= odds_change_points
                ):
                    return True, f"odds moved {abs(a - b) * 100:.0f} points"
            continue  # range and base-rate jitter alone never trigger a run
        if before.value != after.value:
            return True, f"fact changed: {key}"
    return False, "no meaningful change"
