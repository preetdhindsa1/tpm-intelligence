"""SimPy review model: determinism and the direction of every knob (ADR-0012)."""

from __future__ import annotations

import statistics

from simulator.calibrate import Path
from simulator.model import PoolSpec, SimPR, simulate

ONE_ROUND = Path(rounds=1, waits_days=(2.0,), merges=True, final_days=0.5)


def spec(**kw: float) -> PoolSpec:
    base: dict[str, float] = {
        "reviewers": 1,
        "effort_days": 0.5,
        "first_scale": 0.5,
        "follow_scale": 0.5,
    }
    base.update(kw)
    return PoolSpec(**base)  # type: ignore[arg-type]


def crowd(n: int = 30) -> list[SimPR]:
    return [SimPR(f"pr#{i}", "sig/node", ONE_ROUND, opened_at=0.0) for i in range(n)]


def mean_wait(pool: PoolSpec, prs: list[SimPR] | None = None, until: float = 400) -> float:
    res = simulate(prs or crowd(), {"sig/node": pool}, until=until, seed=1)
    return statistics.mean(w for r in res for _, w in r.round_waits)


def test_same_seed_same_result() -> None:
    a = simulate(crowd(), {"sig/node": spec()}, until=100, seed=7)
    b = simulate(crowd(), {"sig/node": spec()}, until=100, seed=7)
    assert [r.merged_at for r in a] == [r.merged_at for r in b]


def test_visible_wait_is_delay_plus_queue_plus_effort() -> None:
    (r,) = simulate(
        [SimPR("pr#1", "sig/node", ONE_ROUND)],
        {"sig/node": spec(effort_days=0.0)},
        until=10,
        seed=1,
    )
    assert r.round_waits == [(1.0, 1.0)]  # 2 days x scale 0.5, no queue, no effort
    assert r.merged_at == 1.5


def test_more_reviewers_shorten_waits_under_load() -> None:
    assert mean_wait(spec(reviewers=5)) < mean_wait(spec(reviewers=1))


def test_new_reviewers_help_less_than_experienced_ones() -> None:
    experienced = mean_wait(spec(reviewers=3))
    ramping = mean_wait(spec(reviewers=1, new_reviewers=2, ramp_weeks=8))
    assert experienced < ramping < mean_wait(spec(reviewers=1))


def test_interruptions_lengthen_waits() -> None:
    assert mean_wait(spec(interruption=0.5)) > mean_wait(spec())


def test_lgtm_only_prs_skip_review_and_unmerged_prs_never_merge() -> None:
    lgtm = Path(0, (), True, 3.0)
    abandoned = Path(1, (1.0,), False, 0.0)
    res = simulate(
        [SimPR("a", "sig/node", lgtm), SimPR("b", "sig/node", abandoned)],
        {"sig/node": spec()},
        until=50,
        seed=1,
    )
    assert (res[0].round_waits, res[0].merged_at) == ([], 3.0)
    assert res[1].merged_at is None
    assert len(res[1].round_waits) == 1


def test_no_reviewers_means_no_reviews() -> None:
    res = simulate(crowd(3), {"sig/node": spec(reviewers=0)}, until=50, seed=1)
    assert all(r.merged_at is None and not r.round_waits for r in res)


def test_in_flight_pr_counts_time_already_waited() -> None:
    pr = SimPR("pr#1", "sig/node", ONE_ROUND, opened_at=-0.75)
    (r,) = simulate([pr], {"sig/node": spec(effort_days=0.0)}, until=10, seed=1)
    assert r.round_waits[0][0] == 0.25  # 1 day of delay, 0.75 already passed
