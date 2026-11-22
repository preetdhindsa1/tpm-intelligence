"""Deterministic checks on an AI link suggestion (ADR-0011). Pure, no I/O.

The suggester answers with a feature key (or none) and two quotes. A suggestion is kept
only when:

1. the feature is on the shortlist the model was given (it cannot invent a feature);
2. ``pr_quote`` appears word for word in the PR text the model was shown, and has at least
   one meaningful word (not just "the code");
3. ``feature_quote`` appears word for word in that feature's title, summary or gate names.

Matching ignores case and runs of whitespace. A kept suggestion is still only
``suggested``: a person must confirm it before it counts (CLAUDE.md section 2.2).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from linker.candidates import Candidate, words

# Confidence of an AI link, before and after a person confirms it.
AI_SUGGESTED_CONFIDENCE = Decimal("0.30")
PERSON_CONFIRMED_CONFIDENCE = Decimal("0.85")


class Outcome(StrEnum):
    """What happened to one suggester answer."""

    SUGGESTED = "suggested"  # passed every check; waits for a person
    NONE = "none"  # the model said the PR belongs to no candidate
    DROPPED = "dropped"  # failed a check; never shown as a link


class DropReason(StrEnum):
    """Why an answer was dropped."""

    NOT_ON_SHORTLIST = "not_on_shortlist"
    PR_QUOTE_NOT_FOUND = "pr_quote_not_found"
    PR_QUOTE_EMPTY = "pr_quote_has_no_meaningful_word"
    FEATURE_QUOTE_NOT_FOUND = "feature_quote_not_found"


@dataclass(frozen=True)
class CheckedSuggestion:
    """The verdict on one answer."""

    outcome: Outcome
    feature_key: str | None
    reason: DropReason | None = None
    rank: int | None = None  # shortlist rank of the chosen feature


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _found(quote: str, *texts: str) -> bool:
    q = _norm(quote)
    return bool(q) and any(q in _norm(t) for t in texts)


def check_suggestion(
    feature_key: str | None,
    pr_quote: str,
    feature_quote: str,
    shown_pr_text: str,
    candidates: Sequence[Candidate],
) -> CheckedSuggestion:
    """Apply the checks in the module docstring, in order."""
    if feature_key is None:
        return CheckedSuggestion(Outcome.NONE, None)
    chosen = next((c for c in candidates if c.feature.key == feature_key), None)
    if chosen is None:
        return CheckedSuggestion(Outcome.DROPPED, feature_key, DropReason.NOT_ON_SHORTLIST)
    if not _found(pr_quote, shown_pr_text):
        return CheckedSuggestion(
            Outcome.DROPPED, feature_key, DropReason.PR_QUOTE_NOT_FOUND, chosen.rank
        )
    if not words(pr_quote):
        return CheckedSuggestion(
            Outcome.DROPPED, feature_key, DropReason.PR_QUOTE_EMPTY, chosen.rank
        )
    f = chosen.feature
    if not _found(feature_quote, f.title, f.summary, *f.feature_gates):
        return CheckedSuggestion(
            Outcome.DROPPED, feature_key, DropReason.FEATURE_QUOTE_NOT_FOUND, chosen.rank
        )
    return CheckedSuggestion(Outcome.SUGGESTED, feature_key, rank=chosen.rank)
