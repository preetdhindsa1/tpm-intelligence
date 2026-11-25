"""Development-lab facts for a repository that tracks its own pull requests.

Pure. No I/O. Every number is a count or a duration from pull requests already
observed. A what-if replays those pull requests. It does not forecast a release
and it does not call the review simulator.

Lane match order is label, then branch prefix, then trailer. A contributor
login is not a lane. ``dependabot[bot]`` and a ``dependabot/`` branch are their
own bucket, never ``cursor``.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from statistics import median
from typing import Any, Literal

from engine.projection import PullRequest, World
from engine.review_rounds import ReviewRound, review_rounds

SMALL_SAMPLE_BELOW = 20
AGENT_LANES = frozenset({"claude", "cursor"})


@dataclass(frozen=True)
class LaneSpec:
    """One lane, in the order the team file listed it."""

    name: str
    labels: tuple[str, ...]
    branch_prefixes: tuple[str, ...]
    trailers: tuple[str, ...]


@dataclass(frozen=True)
class Collision:
    """Two open pull requests share a path, or GitHub reports a conflict with the base."""

    kind: Literal["shared_files", "merge_conflict"]
    pull_requests: tuple[str, ...]
    paths: tuple[str, ...] = ()
    truncated: bool = False


@dataclass(frozen=True)
class WeekCount:
    week: str  # ISO year-week, ``2026-W48``
    lane: str
    count: int


@dataclass(frozen=True)
class DayCount:
    day: str  # ``YYYY-MM-DD``
    count: int


@dataclass(frozen=True)
class CapReplay:
    """Open-agent-PR cap applied to pull requests that already exist."""

    observed_max_open: int
    held: int
    scenario_max_open: int | None
    comparable: bool
    assumption: str


@dataclass(frozen=True)
class FirstPass:
    """Observed wait before the first human review round."""

    observed_median_hours: float | None
    n: int
    waiting: int
    comparable: bool
    assumption: str


@dataclass(frozen=True)
class SizeCap:
    """How many real pull requests exceed a line cap, and how many splits that implies."""

    over_cap: int
    extra_pull_requests: int | None
    comparable: bool
    assumption: str


@dataclass(frozen=True)
class BucketCount:
    """Opened, merged, and still open in one lane, Dependabot, or unassigned."""

    lane: str
    opened: int
    merged: int
    still_open: int


@dataclass(frozen=True)
class LabReport:
    """Counts for one window. ``small_sample`` is a label, not a filled-in forecast."""

    release_key: str
    as_of: datetime
    n_pull_requests: int
    n_merged: int
    n_open: int
    small_sample: bool
    buckets: tuple[BucketCount, ...]
    approval_rate: float | None
    approved_merged: int
    median_hours_to_merge: float | None
    arrivals: tuple[WeekCount, ...]
    queue: tuple[DayCount, ...]
    time_to_first_review_hours: tuple[float, ...]
    still_waiting: int
    review_round_counts: tuple[int, ...]
    review_rounds_median: float | None
    rework: int
    ci_failures: int
    collisions: tuple[Collision, ...]
    cap: CapReplay
    first_pass: FirstPass
    size: SizeCap
    pod: dict[str, Any] | None = None  # engine.pod facts; teams with agent lanes only


def bucket_of(
    labels: tuple[str, ...] | list[str],
    head_ref: str | None,
    texts: tuple[str, ...] | list[str],
    rules: tuple[LaneSpec, ...] | list[LaneSpec],
    author: str | None = None,
) -> str:
    """Lane, else Dependabot, else unassigned. Dependabot is never ``cursor``."""
    lane = classify_lane(labels, head_ref, texts, rules)
    if lane is not None:
        return lane
    ref = head_ref or ""
    if ref.startswith("dependabot/") or author == "dependabot[bot]":
        return "dependabot"
    return "unassigned"


def classify_lane(
    labels: tuple[str, ...] | list[str],
    head_ref: str | None,
    texts: tuple[str, ...] | list[str],
    rules: tuple[LaneSpec, ...] | list[LaneSpec],
) -> str | None:
    """Lane for one pull request, or None when no rule matches.

    Label, then branch prefix, then trailer. Within each step the first rule
    in ``rules`` wins. Matching is case-sensitive. The author login is ignored.
    """
    present = set(labels)
    for rule in rules:
        if present & set(rule.labels):
            return rule.name
    for rule in rules:
        if head_ref and any(head_ref.startswith(prefix) for prefix in rule.branch_prefixes):
            return rule.name
    blob = "\n".join(texts)
    for rule in rules:
        if any(trailer in blob for trailer in rule.trailers):
            return rule.name
    return None


def collisions(prs: tuple[PullRequest, ...] | list[PullRequest]) -> tuple[Collision, ...]:
    """Open pull requests that share a path, plus any GitHub merge conflict with the base.

    An empty file list is not an overlap. A truncated list still reports the paths
    both sides are known to share, and marks the collision truncated.
    """
    open_prs = [pr for pr in prs if pr.state == "open"]
    found: list[Collision] = []
    for i, left in enumerate(open_prs):
        if left.mergeable == "conflicting":
            found.append(Collision("merge_conflict", (left.key,)))
        left_paths = set(left.changed_files)
        if not left_paths:
            continue
        for right in open_prs[i + 1 :]:
            shared = left_paths & set(right.changed_files)
            if not shared:
                continue
            found.append(
                Collision(
                    "shared_files",
                    tuple(sorted((left.key, right.key))),
                    tuple(sorted(shared)),
                    truncated=left.files_truncated or right.files_truncated,
                )
            )
    return tuple(found)


def lab_report(
    world: World,
    release_key: str,
    rules: tuple[LaneSpec, ...] | list[LaneSpec],
    reviewer_pool: tuple[str, ...] | list[str],
    *,
    cap_n: int = 2,
    max_lines: int = 400,
    since: datetime | None = None,
) -> LabReport:
    """Counts for pull requests opened in the window.

    ``since`` is the lower bound. ``None`` counts every pull request opened by
    ``as_of`` (the history of this repository). A release passes its cycle start.
    """
    window = _in_window(world, since)
    lanes = {pr.key: _bucket(pr, rules) for pr in window}
    pool = set(reviewer_pool)
    rounds = {pr.key: tuple(review_rounds(pr)) for pr in window}
    merged = [pr for pr in window if pr.merged_at is not None]
    approved = [pr for pr in merged if _approved(rounds[pr.key])]
    small = len(merged) < SMALL_SAMPLE_BELOW
    waits = _first_review_hours(window, rounds)
    waiting = sum(1 for pr in window if not rounds[pr.key])
    round_counts = tuple(len(rounds[pr.key]) for pr in window)
    found = collisions(window)
    merge_hours = [
        (pr.merged_at - pr.created_at).total_seconds() / 3600
        for pr in merged
        if pr.merged_at is not None
    ]
    return LabReport(
        release_key=release_key,
        as_of=world.as_of,
        n_pull_requests=len(window),
        n_merged=len(merged),
        n_open=sum(1 for pr in window if pr.state == "open"),
        small_sample=small,
        buckets=tuple(_buckets(window, lanes)),
        approval_rate=(len(approved) / len(merged)) if merged else None,
        approved_merged=len(approved),
        median_hours_to_merge=float(median(merge_hours)) if merge_hours else None,
        arrivals=tuple(_arrivals(window, lanes)),
        queue=tuple(_queue(window, rounds, pool, since, world.as_of)),
        time_to_first_review_hours=tuple(waits),
        still_waiting=waiting,
        review_round_counts=round_counts,
        review_rounds_median=float(median(round_counts)) if round_counts else None,
        rework=sum(1 for pr in window if _rework(pr, rounds[pr.key])),
        ci_failures=sum(1 for pr in window if any(c.conclusion == "failure" for c in pr.checks)),
        collisions=found,
        cap=cap_open_agent_prs(window, lanes, cap_n, n_merged=len(merged)),
        first_pass=ai_first_pass(waits, still_waiting=waiting, n_merged=len(merged)),
        size=smaller_pr_cap(window, max_lines, n_merged=len(merged)),
        pod=_pod(window, lanes, rules, len(found), world.as_of, tuple(sorted(pool))),
    )


def _pod(
    prs: list[PullRequest],
    lanes: dict[str, str],
    rules: tuple[LaneSpec, ...] | list[LaneSpec],
    collisions_n: int,
    as_of: datetime,
    approvers: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    from engine.pod import pod_facts  # engine.pod imports this module

    if not rules:
        return None
    return pod_facts(prs, lanes, rules, collisions_n, as_of, approvers=sorted(approvers))


def cap_open_agent_prs(
    prs: list[PullRequest],
    lanes: dict[str, str],
    n: int,
    *,
    n_merged: int,
) -> CapReplay:
    """Replay: hold an agent pull request while ``n`` agent pull requests are already open.

    Human pull requests do not use a slot. ``scenario_max_open`` is omitted when
    fewer than :data:`SMALL_SAMPLE_BELOW` pull requests have merged.
    """
    observed, held, scenario = _replay_cap(prs, lanes, n)
    comparable = n_merged >= SMALL_SAMPLE_BELOW
    return CapReplay(
        observed_max_open=observed,
        held=held,
        scenario_max_open=scenario if comparable else None,
        comparable=comparable,
        assumption=(
            f"If an agent pull request would have made more than {n} agent pull requests "
            "open at once, it waits for one to merge or close. Counted from pull requests "
            "already opened. Not a forecast of future arrivals."
        ),
    )


def ai_first_pass(hours: list[float], *, still_waiting: int, n_merged: int) -> FirstPass:
    """The observed median wait. The scenario does not invent a second median."""
    return FirstPass(
        observed_median_hours=float(median(hours)) if hours else None,
        n=len(hours),
        waiting=still_waiting,
        comparable=n_merged >= SMALL_SAMPLE_BELOW,
        assumption=(
            "An automated first pass would remove the wait before the first human review. "
            "That difference is an assumption, not a measurement, so no second number is shown."
        ),
    )


def smaller_pr_cap(prs: list[PullRequest], max_lines: int, *, n_merged: int) -> SizeCap:
    """Pull requests over ``max_lines`` (additions + deletions), and the splits that implies."""
    over = 0
    extra = 0
    for pr in prs:
        size = pr.additions + pr.deletions
        if max_lines <= 0 or size <= max_lines:
            continue
        over += 1
        extra += ceil(size / max_lines) - 1
    comparable = n_merged >= SMALL_SAMPLE_BELOW
    return SizeCap(
        over_cap=over,
        extra_pull_requests=extra if comparable else None,
        comparable=comparable,
        assumption=(
            f"A pull request over {max_lines} changed lines would be split. "
            "The extra count is how many additional pull requests those real sizes imply. "
            "No calendar of future work is created."
        ),
    )


def extra_for_sizes(sizes: list[int], max_lines: int) -> int:
    """``ceil(size / cap) - 1`` summed over sizes above the cap. Zero-size is not over."""
    extra = 0
    for size in sizes:
        if max_lines > 0 and size > max_lines:
            extra += ceil(size / max_lines) - 1
    return extra


def _bucket(pr: PullRequest, rules: tuple[LaneSpec, ...] | list[LaneSpec]) -> str:
    texts = [pr.body, *(note.message for note in pr.commits)]
    return bucket_of(pr.labels, pr.head_ref, texts, rules, pr.author)


def _approved(rounds: tuple[ReviewRound, ...]) -> bool:
    """An approving review round. Merging without one does not count."""
    return any(rnd.outcome == "approved" for rnd in rounds)


def _buckets(prs: list[PullRequest], lanes: dict[str, str]) -> list[BucketCount]:
    opened: dict[str, int] = defaultdict(int)
    merged: dict[str, int] = defaultdict(int)
    still: dict[str, int] = defaultdict(int)
    for pr in prs:
        lane = lanes[pr.key]
        opened[lane] += 1
        if pr.merged_at is not None:
            merged[lane] += 1
        if pr.state == "open":
            still[lane] += 1
    return [BucketCount(lane, opened[lane], merged[lane], still[lane]) for lane in sorted(opened)]


def _in_window(world: World, since: datetime | None) -> list[PullRequest]:
    out = []
    for pr in world.pull_requests.values():
        if since is not None and pr.created_at < since:
            continue
        if pr.created_at > world.as_of:
            continue
        out.append(pr)
    out.sort(key=lambda pr: (pr.created_at, pr.key))
    return out


def _arrivals(prs: list[PullRequest], lanes: dict[str, str]) -> list[WeekCount]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for pr in prs:
        year, week, _ = pr.created_at.isocalendar()
        counts[(f"{year}-W{week:02d}", lanes[pr.key])] += 1
    return [WeekCount(week, lane, n) for (week, lane), n in sorted(counts.items())]


def _queue(
    prs: list[PullRequest],
    rounds: dict[str, tuple[ReviewRound, ...]],
    pool: set[str],
    since: datetime | None,
    as_of: datetime,
) -> list[DayCount]:
    start = since if since is not None else (min(pr.created_at for pr in prs) if prs else None)
    if start is None or start > as_of:
        return []
    day = start.date()
    last = as_of.date()
    points: list[DayCount] = []
    while day <= last:
        end = datetime(day.year, day.month, day.day, tzinfo=as_of.tzinfo) + timedelta(days=1)
        waiting = 0
        for pr in prs:
            if pr.created_at >= end:
                continue
            if pr.merged_at is not None and pr.merged_at < end:
                continue
            if pr.closed_at is not None and pr.closed_at < end:
                continue
            reviewed = any(rnd.reviewer in pool and rnd.started_at < end for rnd in rounds[pr.key])
            if not reviewed:
                waiting += 1
        points.append(DayCount(day.isoformat(), waiting))
        day += timedelta(days=1)
    return points


def _first_review_hours(
    prs: list[PullRequest], rounds: dict[str, tuple[ReviewRound, ...]]
) -> list[float]:
    hours: list[float] = []
    for pr in prs:
        if not rounds[pr.key]:
            continue
        first = rounds[pr.key][0]
        hours.append((first.started_at - pr.created_at).total_seconds() / 3600)
    return hours


def _rework(pr: PullRequest, rounds: tuple[ReviewRound, ...]) -> bool:
    if any(rnd.outcome == "changes_requested" for rnd in rounds):
        return True
    if not rounds:
        return False
    first = rounds[0].started_at
    return any(note.committed_at > first for note in pr.commits)


def _replay_cap(prs: list[PullRequest], lanes: dict[str, str], n: int) -> tuple[int, int, int]:
    """Return observed max open, how many were held, and the capped max."""
    events: list[tuple[datetime, int, str, PullRequest]] = []
    for pr in prs:
        if lanes.get(pr.key) not in AGENT_LANES:
            continue
        events.append((pr.created_at, 1, "open", pr))
        closed = pr.merged_at or pr.closed_at
        if closed is not None:
            events.append((closed, 0, "close", pr))
    events.sort(key=lambda item: (item[0], item[1], item[3].key))
    observed: set[str] = set()
    capped: set[str] = set()
    held: deque[str] = deque()
    held_n = 0
    max_observed = 0
    max_capped = 0
    for _at, _order, kind, pr in events:
        if kind == "close":
            observed.discard(pr.key)
            capped.discard(pr.key)
            while held and len(capped) < n:
                capped.add(held.popleft())
            max_capped = max(max_capped, len(capped))
            continue
        observed.add(pr.key)
        max_observed = max(max_observed, len(observed))
        if len(capped) >= n:
            held.append(pr.key)
            held_n += 1
        else:
            capped.add(pr.key)
        max_capped = max(max_capped, len(capped))
    return max_observed, held_n, max_capped
