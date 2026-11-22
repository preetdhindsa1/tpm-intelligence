"""Fact checker: verify every claim against the fact sheet (CLAUDE.md section 8). Pure.

Verdicts:

* ``verified``: every ref exists, the value matches the primary fact, and every number in
  the text matches a cited fact.
* ``removed`` with a reason:
  * ``no_supporting_data``: no refs, an unknown ref, or no value to check.
  * ``type_mismatch``: the claim's type is not the primary fact's kind.
  * ``wrong_value``: the value does not match the primary fact.
  * ``text_mismatch``: the sentence states a number no cited fact supports.

Removed claims are never shown. Their counts are kept and published.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from verify.claims import Claim, ClaimValue
from verify.facts import Fact, FactKind, FactSheet
from verify.numbers import stated_numbers

PROBABILITY_TOLERANCE = 0.01  # one percentage point: summaries round odds to whole percents
DURATION_TOLERANCE_DAYS = 0.5
DATE_TOLERANCE_SECONDS = 60.0  # minute precision ("12:05 UTC")


class Verdict(StrEnum):
    """Outcome for one claim."""

    VERIFIED = "verified"
    REMOVED = "removed"


class Reason(StrEnum):
    """Why a claim was removed."""

    NO_SUPPORTING_DATA = "no_supporting_data"
    TYPE_MISMATCH = "type_mismatch"
    WRONG_VALUE = "wrong_value"
    TEXT_MISMATCH = "text_mismatch"


@dataclass(frozen=True)
class CheckedClaim:
    """A claim with its verdict and, when removed, the reason and the true value."""

    claim: Claim
    verdict: Verdict
    reason: Reason | None = None
    detail: str | None = None


@dataclass(frozen=True)
class CheckReport:
    """All verdicts for one agent output, plus counts to store and publish."""

    checked: tuple[CheckedClaim, ...]

    @property
    def verified(self) -> tuple[Claim, ...]:
        """Claims that may be shown."""
        return tuple(c.claim for c in self.checked if c.verdict is Verdict.VERIFIED)

    @property
    def counts(self) -> dict[str, int]:
        """``verified`` plus one count per removal reason (zeros included)."""
        out = {"verified": 0, **{f"removed.{r.value}": 0 for r in Reason}}
        for key, n in Counter(
            "verified" if c.reason is None else f"removed.{c.reason.value}" for c in self.checked
        ).items():
            out[key] = n
        return out

    @property
    def removal_rate(self) -> float | None:
        """Removed / total (None for an empty output)."""
        if not self.checked:
            return None
        return sum(c.verdict is Verdict.REMOVED for c in self.checked) / len(self.checked)


def check_claims(claims: Iterable[Claim], facts: FactSheet) -> CheckReport:
    """Verify each claim independently."""
    return CheckReport(tuple(check_claim(c, facts) for c in claims))


def check_claim(claim: Claim, facts: FactSheet) -> CheckedClaim:
    """Verify one claim (see module docstring for the order of checks)."""

    def removed(reason: Reason, detail: str) -> CheckedClaim:
        return CheckedClaim(claim, Verdict.REMOVED, reason, detail)

    if not claim.refs:
        return removed(Reason.NO_SUPPORTING_DATA, "claim cites no facts")
    missing = [r for r in claim.refs if r not in facts]
    if missing:
        return removed(Reason.NO_SUPPORTING_DATA, f"unknown fact(s): {', '.join(missing)}")
    if claim.value is None:
        return removed(Reason.NO_SUPPORTING_DATA, "claim states no checkable value")
    primary = facts[claim.refs[0]]
    if claim.type is not primary.kind:
        return removed(
            Reason.TYPE_MISMATCH, f"claim type {claim.type.value}, fact is {primary.kind.value}"
        )
    if not values_match(primary, claim.value):
        return removed(Reason.WRONG_VALUE, f"fact {primary.key} = {primary.value!r}")
    cited = [facts[r] for r in claim.refs]
    identifiers = _identifier_numbers(claim.refs)
    unsupported = [
        n
        for n in stated_numbers(claim.text)
        if n not in identifiers and not _number_supported(n, cited)
    ]
    if unsupported:
        shown = ", ".join(f"{n:g}" for n in unsupported)
        return removed(Reason.TEXT_MISMATCH, f"text states {shown}, not in the cited facts")
    return CheckedClaim(claim, Verdict.VERIFIED)


# ---------------------------------------------------------------- value comparison


def values_match(fact: Fact, claimed: ClaimValue) -> bool:
    """Compare a claimed value with a fact using the fact kind's tolerance."""
    actual = fact.value
    if actual is None:
        return False
    match fact.kind:
        case FactKind.COUNT:
            n = _as_number(claimed)
            return n is not None and n == float(_num(actual)) and float(n).is_integer()
        case FactKind.PROBABILITY:
            p = _as_number(claimed)
            return p is not None and 0 <= p <= 1 and abs(p - _num(actual)) <= PROBABILITY_TOLERANCE
        case FactKind.DURATION_DAYS:
            d = _as_number(claimed)
            return d is not None and abs(d - _num(actual)) <= DURATION_TOLERANCE_DAYS
        case FactKind.BOOLEAN:
            return isinstance(claimed, bool) and claimed is actual
        case FactKind.LABEL:
            return isinstance(claimed, str) and claimed.strip().lower() == str(actual).lower()
        case FactKind.DATE:
            return isinstance(actual, datetime) and _dates_match(actual, claimed)
    return False  # pragma: no cover - exhaustive


def _num(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"numeric fact expected, got {value!r}")
    return float(value)


def _as_number(value: ClaimValue) -> float | None:
    if isinstance(value, bool) or value is None or isinstance(value, datetime):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(value)
    except ValueError:
        return None


def _dates_match(actual: datetime, claimed: ClaimValue) -> bool:
    actual = actual.astimezone(UTC)
    if isinstance(claimed, str):
        text = claimed.strip()
        if len(text) == 10:  # YYYY-MM-DD: same UTC calendar day
            try:
                return date.fromisoformat(text) == actual.date()
            except ValueError:
                return False
        try:
            claimed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return False
    if not isinstance(claimed, datetime) or claimed.tzinfo is None:
        return False  # naive times are ambiguous
    return abs((claimed - actual).total_seconds()) <= DATE_TOLERANCE_SECONDS


# ---------------------------------------------------------------- numbers in the text


def _identifier_numbers(refs: Sequence[str]) -> set[float]:
    """Numbers inside the cited subjects' keys ("Feature 6395" when citing #6395's facts).

    Only the subject part (before ``::``) counts, so a field name can never whitelist a value.
    """
    return {float(n) for ref in refs for n in re.findall(r"\d+", ref.split("::", 1)[0])}


def _number_supported(n: float, cited: Sequence[Fact]) -> bool:
    """Does a number stated in the text match one of the cited facts?"""
    for fact in cited:
        v = fact.value
        if isinstance(v, bool) or not isinstance(v, int | float):
            continue
        match fact.kind:
            case FactKind.COUNT:
                if n == v:
                    return True
            case FactKind.PROBABILITY:
                # "38%" or "0.38" for 0.384
                if abs(n - v * 100) <= 100 * PROBABILITY_TOLERANCE or abs(n - v) <= 0.005:
                    return True
            case FactKind.DURATION_DAYS:
                if abs(n - v) <= DURATION_TOLERANCE_DAYS:
                    return True
            case _:
                pass
    return False
