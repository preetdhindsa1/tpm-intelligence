"""SimPy model of PRs moving through review (ADR-0012). No I/O; fixed seeds.

A PR follows a real **path** (``simulator.calibrate.Path``): its number of review rounds,
the real wait before each round, whether it merged, and the delay from its last round to
merge. PRs approved without GitHub reviews skip review entirely.

Before each round:

1. **Delay that blocks nobody**: the real wait before that round x the pool's fitted
   *scale* (``first_scale`` for a PR's first round, ``follow_scale`` for later ones). This is
   author fixes, CI, time zones and everything else that is not reviewer queueing. Using
   each PR's real wait keeps the long tail of real reviews.
2. **Queue** for one of the pool's reviewers.
3. **Reviewer effort**: an exponential time with mean ``effort_days`` (fitted, see
   ``simulator.replay``), during which that reviewer can do nothing else.

The round is visible when the effort ends: visible wait = delay + queue + effort.

* **Interruptions** remove a share of reviewer time: effort takes ``1 / (1 - share)``
  longer.
* **New reviewers** start at 10% speed and ramp up linearly to full speed over
  ``ramp_weeks``.

Times are in days from the start of the simulation.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import simpy

from simulator.calibrate import Path

RAMP_START = 0.10
MAX_INTERRUPTION = 0.9


@dataclass(frozen=True)
class PoolSpec:
    """Staffing and speed of one pool in one run."""

    reviewers: int
    effort_days: float
    first_scale: float
    follow_scale: float
    interruption: float = 0.0  # share of reviewer time lost, 0..0.9
    new_reviewers: int = 0
    ramp_weeks: float = 0.0

    @property
    def capacity(self) -> int:
        """Reviewers available, including new ones."""
        return max(self.reviewers, 0) + max(self.new_reviewers, 0)


@dataclass(frozen=True)
class SimPR:
    """One PR to simulate."""

    key: str
    pool: str
    path: Path
    opened_at: float = 0.0  # days; negative for PRs already open at the start
    done_rounds: int = 0  # rounds already finished before the start
    previous_visible: float | None = None  # when the last finished round was visible
    final_delay: float | None = None  # overrides path.final_days (for in-flight PRs)


@dataclass
class PRResult:
    """What happened to one PR."""

    key: str
    pool: str
    opened_at: float
    round_waits: list[tuple[float, float]] = field(default_factory=list)  # (visible at, wait)
    merged_at: float | None = None


@dataclass(frozen=True)
class _Reviewer:
    ramp_days: float

    def speed(self, now: float) -> float:
        if self.ramp_days <= 0:
            return 1.0
        return min(1.0, RAMP_START + (1 - RAMP_START) * now / self.ramp_days)


def simulate(
    prs: Sequence[SimPR],
    pools: Mapping[str, PoolSpec],
    until: float,
    seed: int,
    effort_draws: Sequence[np.ndarray[Any, Any]] | None = None,
) -> list[PRResult]:
    """Run once until ``until`` days; the same inputs and seed give the same result.

    ``effort_draws`` (one unit-mean exponential per remaining round, per PR) lets a caller
    hold each PR's random numbers fixed between a baseline and a scenario
    (``simulator.scenario``). Without it, draws come from ``seed`` in PR order.
    """
    rng = np.random.default_rng(seed)
    env = simpy.Environment()
    stores: dict[str, Any] = {}
    for name, spec in pools.items():
        store = simpy.Store(env)
        for _ in range(max(spec.reviewers, 0)):
            store.put(_Reviewer(0.0))
        for _ in range(max(spec.new_reviewers, 0)):
            store.put(_Reviewer(spec.ramp_weeks * 7))
        stores[name] = store
    results = [PRResult(p.key, p.pool, p.opened_at) for p in prs]
    # Effort draws per PR, made up front: a scenario that changes one pool does not shift
    # the random numbers of PRs elsewhere (common random numbers for baseline vs scenario).
    draws: Sequence[np.ndarray[Any, Any]] = (
        effort_draws
        if effort_draws is not None
        else [rng.exponential(1.0, size=max(p.path.rounds, 0)) for p in prs]
    )

    def run(pr: SimPR, out: PRResult, unit: Any) -> Generator[Any, Any, None]:
        spec = pools.get(pr.pool)
        if pr.opened_at > 0:
            yield env.timeout(pr.opened_at)
        previous = pr.opened_at if pr.previous_visible is None else pr.previous_visible
        for i in range(pr.done_rounds, pr.path.rounds):
            if spec is None or spec.capacity == 0:
                return  # nobody can review: the PR waits
            scale = spec.first_scale if i == 0 else spec.follow_scale
            delay = pr.path.waits_days[i] * scale - max(0.0, env.now - previous)
            if delay > 0:
                yield env.timeout(delay)
            reviewer = yield stores[pr.pool].get()
            share = 1.0 - min(max(spec.interruption, 0.0), MAX_INTERRUPTION)
            effort = float(unit[i]) * spec.effort_days
            yield env.timeout(effort / (reviewer.speed(env.now) * share))
            stores[pr.pool].put(reviewer)
            out.round_waits.append((env.now, env.now - previous))
            previous = env.now
        if pr.path.merges:
            final = pr.path.final_days if pr.final_delay is None else pr.final_delay
            yield env.timeout(max(final, 0.0))
            out.merged_at = env.now

    for pr, out, unit in zip(prs, results, draws, strict=True):
        env.process(run(pr, out, unit))
    env.run(until=until)
    return results
