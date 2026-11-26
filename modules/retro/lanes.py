"""A sprint retro for a repository that tracks its own pod, per lane (#182). Pure, no I/O.

Lanes are the pod's roles (ADR-0023: a person's lane, agent lanes, bots), never logins.
Counts come from pull requests opened in the window; a lane with fewer than
``SMALL_SAMPLE_BELOW`` merged PRs is labelled a small sample, not compared.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from engine.lab import LaneSpec, had_rework, lane_of
from engine.projection import PullRequest, World
from engine.review_rounds import review_rounds

SMALL_SAMPLE_BELOW = 10  # the minimum group size for comparisons (CLAUDE.md section 6)
# This repo's UX v1 sprint (Wave 1, docs/plan/e2e-plan.md): from the Wave 0 merge to the
# close of its last issue (#158). Set from the repository's own history.
UX_V1_SPRINT = (datetime.fromisoformat("2026-11-24T22:55:22+00:00"),
                datetime.fromisoformat("2026-11-25T13:01:19+00:00"))  # fmt: skip


@dataclass(frozen=True)
class LaneRetro:
    lane: str
    opened: int
    merged: int
    still_open: int
    median_hours_to_merge: float | None
    review_rounds_median: float | None
    rework: int  # changes requested, or commits after the first review
    ci_failed: int  # any failing check on the latest commit
    small_sample: bool


def _median(values: Sequence[float]) -> float | None:
    return round(float(median(values)), 1) if values else None


def lane_retro(
    world: World, rules: Sequence[LaneSpec], since: datetime, until: datetime
) -> list[LaneRetro]:
    """Per lane, the PRs opened in ``[since, until]`` and what happened to them by ``as_of``."""
    by_lane: dict[str, list[PullRequest]] = defaultdict(list)
    for pr in world.pull_requests.values():
        if since <= pr.created_at <= until:
            by_lane[lane_of(pr, list(rules))].append(pr)
    out = []
    for lane, prs in sorted(by_lane.items()):
        merged = [p for p in prs if p.merged_at is not None]
        hours = [(p.merged_at - p.created_at).total_seconds() / 3600
                 for p in merged if p.merged_at is not None]  # fmt: skip
        out.append(LaneRetro(
            lane, len(prs), len(merged), sum(p.state == "open" for p in prs), _median(hours),
            _median([len(review_rounds(p)) for p in prs]), sum(had_rework(p) for p in prs),
            sum(any(c.conclusion == "failure" for c in p.checks) for p in prs),
            len(merged) < SMALL_SAMPLE_BELOW,
        ))  # fmt: skip
    return out
