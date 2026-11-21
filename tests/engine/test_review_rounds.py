"""Review rounds, not raw review records (CLAUDE.md section 6, ADR-0006)."""

from __future__ import annotations

from datetime import timedelta

from engine.projection import PullRequest, Review, project
from engine.review_rounds import review_rounds, review_waits
from tests.engine.conftest import MAIN_PR, fixture_events, utc

T0 = utc(2026, 11, 3, 9)


def pr_with(reviews: list[tuple[str, str, int]], author: str = "author") -> PullRequest:
    """reviews: (reviewer, state, minutes after T0)."""
    return PullRequest(
        key="k/k#1",
        repo="k/k",
        number=1,
        title="t",
        body="",
        author=author,
        labels=(),
        created_at=utc(2026, 11, 1),
        state="open",
        merged_at=None,
        closed_at=None,
        reviews=tuple(
            Review(str(i), who, state, T0 + timedelta(minutes=m))
            for i, (who, state, m) in enumerate(reviews)
        ),
        checks=(),
    )


def test_main_pr_143709_rounds_are_far_fewer_than_records() -> None:
    pr = project(fixture_events(), utc(2027, 1, 1)).pull_requests[MAIN_PR]
    rounds = review_rounds(pr)
    assert len(pr.reviews) == 97
    assert 0 < len(rounds) < len(pr.reviews) / 2
    assert sum(r.review_count for r in rounds) <= len(pr.reviews)
    assert all(r.reviewer != pr.author for r in rounds)


def test_forty_comments_in_one_sitting_are_one_round() -> None:
    rounds = review_rounds(pr_with([("rev-a", "commented", m) for m in range(40)]))
    assert len(rounds) == 1
    assert rounds[0].review_count == 40


def test_gap_longer_than_window_starts_a_new_round() -> None:
    pr = pr_with(
        [("rev-a", "commented", 0), ("rev-a", "commented", 60), ("rev-a", "approved", 121)]
    )
    assert [r.review_count for r in review_rounds(pr)] == [2, 1]


def test_reviewers_are_grouped_separately() -> None:
    pr = pr_with([("rev-a", "commented", 0), ("rev-b", "commented", 5), ("rev-a", "commented", 10)])
    assert sorted((r.reviewer, r.review_count) for r in review_rounds(pr)) == [
        ("rev-a", 2),
        ("rev-b", 1),
    ]


def test_author_replies_and_bots_are_ignored() -> None:
    pr = pr_with(
        [
            ("author", "commented", 0),
            ("ci-bot", "commented", 1),
            ("dependabot[bot]", "approved", 2),
            ("rev-a", "approved", 3),
        ]
    )
    assert [r.reviewer for r in review_rounds(pr)] == ["rev-a"]


def test_outcome_is_last_decisive_state() -> None:
    pr = pr_with(
        [
            ("rev-a", "changes_requested", 0),
            ("rev-a", "commented", 5),
            ("rev-a", "approved", 10),
            ("rev-a", "commented", 15),
        ]
    )
    assert review_rounds(pr)[0].outcome == "approved"
    assert review_rounds(pr_with([("rev-a", "commented", 0)]))[0].outcome == "commented"


def test_review_waits() -> None:
    pr = pr_with([("rev-a", "commented", 0), ("rev-b", "approved", 24 * 60)])
    waits = review_waits(pr, review_rounds(pr))
    assert waits == [T0 - utc(2026, 11, 1), timedelta(days=1)]
