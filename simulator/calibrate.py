"""Measure the simulator's inputs from finished releases (ADR-0012). Pure, no I/O.

Everything here is measured from PRs opened between a release's cycle start and its Code
Freeze. Reviewers are only ever **counted** per SIG, never named or ranked (CLAUDE.md §10).

* **Pool** of a PR: its first ``sig/*`` label in sorted order. SIGs with fewer than
  ``MIN_POOL_PRS`` PRs in the source releases share the ``other`` pool.
* **PR path** (``Path``): how many review rounds it had (ADR-0006), the real wait before each
  round (from opening, or from the previous round), whether it merged, and the delay from
  the last round to merge (or from opening to merge for PRs approved only through
  ``/lgtm`` comments).
* **Reviewers per week** in a pool: each reviewer's week is split across pools by their
  share of rounds there, so a person reviewing in two SIGs is not counted twice.
* **Arrivals**: PRs opened per week per pool.
Reviewer effort per round and the share of each wait that is delay rather than queueing are
*fitted* in ``simulator.replay``, not measured: GitHub shows when a review was posted, not
how long it took, and cannot separate the author's fix time from the reviewer's time.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.projection import PullRequest, World
from engine.review_rounds import review_rounds, review_waits

MIN_POOL_PRS = 100
OTHER = "other"
DAY = 86400.0


def days(delta: timedelta) -> float:
    """A duration in days."""
    return delta.total_seconds() / DAY


def primary_sig(labels: Iterable[str]) -> str:
    """First ``sig/*`` label in sorted order, or ``none``."""
    return next((lb for lb in sorted(labels) if lb.startswith("sig/")), "none")


@dataclass(frozen=True)
class Path:
    """One real PR's way through review, used as a template."""

    rounds: int
    waits_days: tuple[float, ...]  # real wait before each round (len == rounds)
    merges: bool
    final_days: float  # last round -> merge, or open -> merge when rounds == 0


@dataclass(frozen=True)
class PoolInputs:
    """Measured inputs of one reviewer pool."""

    name: str
    prs: int
    reviewers_per_week: float  # median over weeks
    arrivals_per_week: float
    first_wait_median_days: float | None  # fit target: wait before a PR's first round
    follow_wait_median_days: float | None  # fit target: wait before rounds 2..n
    paths: tuple[Path, ...]


@dataclass(frozen=True)
class Window:
    """A release's PR window and the time real data is observed until."""

    release_key: str
    start: datetime
    freeze: datetime
    horizon: datetime


def window(world: World, release_key: str) -> Window:
    """Cycle start to Code Freeze; observed until release day or the end of the data."""
    r = world.releases[release_key]
    if r.cycle_start_at is None or r.code_freeze_at is None:
        raise ValueError(f"{release_key} has no cycle start or Code Freeze date")
    end = r.release_at or world.as_of
    return Window(release_key, r.cycle_start_at, r.code_freeze_at, min(end, world.as_of))


def window_prs(world: World, w: Window) -> list[PullRequest]:
    """PRs opened in the window, oldest first."""
    return sorted(
        (p for p in world.pull_requests.values() if w.start <= p.created_at < w.freeze),
        key=lambda p: (p.created_at, p.key),
    )


def path_of(pr: PullRequest, horizon: datetime) -> Path:
    """The PR's path as observed until ``horizon``."""
    rounds = [r for r in review_rounds(pr) if r.started_at < horizon]
    waits = review_waits(pr, rounds)
    merged = pr.merged_at is not None and pr.merged_at <= horizon
    if not merged:
        final = 0.0
    elif rounds:
        final = max(0.0, days(pr.merged_at - rounds[-1].ended_at))  # type: ignore[operator]
    else:
        final = days(pr.merged_at - pr.created_at)  # type: ignore[operator]
    return Path(len(rounds), tuple(days(x) for x in waits), merged, final)


def reviewer_weeks(
    prs: Sequence[PullRequest], w: Window, pool_of: Mapping[str, str]
) -> dict[str, list[float]]:
    """Per pool, the reviewer count of each week in the window (fractional, see docstring).

    Only weeks that have happened count: for a release still before Code Freeze, the weeks
    after the data end would otherwise count as zero reviewers and pull the median down
    (Kafka 4.5.0 read as 1 reviewer for 176 open PRs, 2026-11-25).
    """
    end = min(w.freeze, w.horizon)
    weeks = max(1, int(days(end - w.start) // 7))
    load: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    for pr in prs:
        for rnd in review_rounds(pr):
            wk = int(days(rnd.started_at - w.start) // 7)
            if 0 <= wk < weeks:
                load[(wk, rnd.reviewer)][pool_of[pr.key]] += 1
    out: dict[str, list[float]] = defaultdict(lambda: [0.0] * weeks)
    for (wk, _), by_pool in load.items():
        total = sum(by_pool.values())
        for pool, n in by_pool.items():
            out[pool][wk] += n / total
    return dict(out)


def pools_for(world: World, release_keys: Sequence[str]) -> list[str]:
    """Pool names with enough PRs across the source releases (plus ``other``)."""
    counts: Counter[str] = Counter()
    for key in release_keys:
        for pr in window_prs(world, window(world, key)):
            counts[primary_sig(pr.labels)] += 1
    return [*sorted(p for p, n in counts.items() if n >= MIN_POOL_PRS and p != "none"), OTHER]


def assign(pr: PullRequest, pools: Sequence[str]) -> str:
    """The pool a PR queues in."""
    sig = primary_sig(pr.labels)
    return sig if sig in pools else OTHER


@dataclass(frozen=True)
class Inputs:
    """Measured inputs over a set of releases."""

    source_releases: tuple[str, ...]
    measured_at: datetime
    pools: Mapping[str, PoolInputs]


def measure(
    world: World, release_keys: Sequence[str], pools: Sequence[str] | None = None
) -> Inputs:
    """Inputs over ``release_keys`` (each observed until its own horizon)."""
    names = list(pools) if pools is not None else pools_for(world, release_keys)
    paths: dict[str, list[Path]] = defaultdict(list)
    first: dict[str, list[float]] = defaultdict(list)
    follow: dict[str, list[float]] = defaultdict(list)
    staff: dict[str, list[float]] = defaultdict(list)
    count: Counter[str] = Counter()
    total_weeks = 0.0
    for key in release_keys:
        w = window(world, key)
        prs = window_prs(world, w)
        pool_of = {p.key: assign(p, names) for p in prs}
        total_weeks += days(w.freeze - w.start) / 7
        for pr in prs:
            pool = pool_of[pr.key]
            count[pool] += 1
            path = path_of(pr, w.horizon)
            paths[pool].append(path)
            rounds = [r for r in review_rounds(pr) if r.started_at < w.horizon]
            if rounds:
                waits = review_waits(pr, rounds)
                first[pool].append(days(waits[0]))
                follow[pool].extend(days(x) for x in waits[1:])
        for pool, weeks in reviewer_weeks(prs, w, pool_of).items():
            staff[pool].extend(weeks)
    return Inputs(
        source_releases=tuple(release_keys),
        measured_at=world.as_of,
        pools={
            name: PoolInputs(
                name=name,
                prs=count[name],
                reviewers_per_week=statistics.median(staff[name]) if staff[name] else 0.0,
                arrivals_per_week=count[name] / total_weeks if total_weeks else 0.0,
                first_wait_median_days=statistics.median(first[name]) if first[name] else None,
                follow_wait_median_days=statistics.median(follow[name]) if follow[name] else None,
                paths=tuple(paths[name]),
            )
            for name in names
        },
    )
