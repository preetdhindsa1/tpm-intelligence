"""Group raw review records into review rounds (ADR-0006). Pure, no I/O.

GitHub stores one review record per "Submit review" click, and some reviewers leave dozens in
one sitting. Counting records would make one careful reviewer look like many rounds. A
**round** is consecutive reviews by the same reviewer where each one follows the previous
within ``window`` (default 60 minutes).

Excluded: the PR author's own review records (replies to review threads create COMMENTED
reviews by the author) and bot accounts (logins ending in ``[bot]`` or ``-bot``).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.projection import PullRequest, Review

DEFAULT_WINDOW = timedelta(minutes=60)
_DECISIVE = ("approved", "changes_requested", "dismissed")


@dataclass(frozen=True)
class ReviewRound:
    """One reviewer's sitting on one PR."""

    reviewer: str
    started_at: datetime
    ended_at: datetime
    review_count: int
    outcome: str  # last decisive state in the round, else "commented"


def is_bot(login: str) -> bool:
    """Heuristic bot detection by login suffix."""
    return login.endswith("[bot]") or login.endswith("-bot")


def review_rounds(pr: PullRequest, window: timedelta = DEFAULT_WINDOW) -> list[ReviewRound]:
    """Rounds on ``pr``, ordered by start time."""
    by_reviewer: dict[str, list[Review]] = defaultdict(list)
    for r in pr.reviews:
        if r.reviewer is None or r.reviewer == pr.author or is_bot(r.reviewer):
            continue
        by_reviewer[r.reviewer].append(r)

    rounds: list[ReviewRound] = []
    for reviewer, items in by_reviewer.items():
        items.sort(key=lambda r: (r.submitted_at, r.id))
        current: list[Review] = [items[0]]
        for r in items[1:]:
            if r.submitted_at - current[-1].submitted_at <= window:
                current.append(r)
            else:
                rounds.append(_close(reviewer, current))
                current = [r]
        rounds.append(_close(reviewer, current))
    return sorted(rounds, key=lambda r: (r.started_at, r.reviewer))


def _close(reviewer: str, items: Sequence[Review]) -> ReviewRound:
    decisive = [r.state for r in items if r.state in _DECISIVE]
    return ReviewRound(
        reviewer=reviewer,
        started_at=items[0].submitted_at,
        ended_at=items[-1].submitted_at,
        review_count=len(items),
        outcome=decisive[-1] if decisive else "commented",
    )


def review_waits(pr: PullRequest, rounds: Sequence[ReviewRound]) -> list[timedelta]:
    """Wait before each round: from PR creation (first) or the previous round's end.

    Measures queue time for calibration (M6). Rounds that overlap the previous one
    (two reviewers at once) have zero wait.
    """
    waits: list[timedelta] = []
    previous_end = pr.created_at
    for rnd in rounds:
        waits.append(max(timedelta(0), rnd.started_at - previous_end))
        previous_end = max(previous_end, rnd.ended_at)
    return waits
