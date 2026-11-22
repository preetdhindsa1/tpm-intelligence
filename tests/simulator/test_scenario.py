"""What-if scenarios: baseline vs scenario, common random numbers, ranges (ADR-0012)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from engine.projection import project
from simulator.calibrate import Inputs, Path, PoolInputs
from simulator.scenario import (
    Calibration,
    InFlight,
    PoolChange,
    Scenario,
    State,
    calibration_from_json,
    calibration_to_json,
    compare,
    current_state,
    horizon,
    run,
    scenario_from_json,
    scenario_to_json,
)
from tests.engine.conftest import MAIN_PR, V138, fixture_events, utc

NOW = datetime(2026, 11, 22, tzinfo=UTC)
PATHS = (
    Path(1, (1.0,), True, 0.5),
    Path(2, (0.5, 1.5), True, 1.0),
    Path(3, (2.0, 0.5, 0.5), False, 0.0),
)


def pool(name: str, arrivals: float = 40.0) -> PoolInputs:
    return PoolInputs(name, 300, 3.0, arrivals, 0.8, 0.6, PATHS)


def calibration(effort: float = 0.5) -> Calibration:
    return Calibration(
        release_key=V138,
        inputs=Inputs(
            ("kubernetes:v1.37",), NOW, {"sig/node": pool("sig/node"), "other": pool("other")}
        ),
        effort_days=effort,
        scales={"sig/node": (0.5, 0.5), "other": (0.5, 0.5)},
        validation={"passed": False},
        data_until=NOW,
    )


def state() -> State:
    in_flight = tuple(
        InFlight(f"pr#{i}", "sig/node" if i % 2 else "other", -3.0, i % 3, -1.0) for i in range(40)
    )
    return State(
        V138,
        NOW,
        NOW + timedelta(days=21),
        "Code Freeze",
        in_flight,
        {"sig/node": 3.0, "other": 2.0},
    )


def wait(o: object, name: str) -> float:
    p = next(p for p in o.pools if p.pool == name)  # type: ignore[attr-defined]
    return p.review_wait_days.median


def test_same_seed_same_result() -> None:
    a = run(calibration(), state(), Scenario(), replications=3)
    b = run(calibration(), state(), Scenario(), replications=3)
    assert a == b


def test_results_are_ranges() -> None:
    o = run(calibration(), state(), Scenario(), replications=5)
    r = o.total.review_wait_days
    assert r is not None
    assert r.low <= r.median <= r.high
    assert o.total.merged is not None
    assert o.total.not_merged is not None


def test_a_change_to_one_pool_leaves_other_pools_identical() -> None:
    c = compare(calibration(), state(), Scenario("cut", {"sig/node": PoolChange(reviewers=-2)}), 4)
    base = next(p for p in c.baseline.pools if p.pool == "other")
    scen = next(p for p in c.scenario.pools if p.pool == "other")
    assert base == scen
    node = next(p for p in c.scenario.pools if p.pool == "sig/node")
    assert node.reviewers == 1


def test_fewer_reviewers_and_more_prs_make_waits_longer() -> None:
    cal, st = calibration(effort=1.0), state()
    base = run(cal, st, Scenario(), 4)
    fewer = run(cal, st, Scenario("fewer", {"sig/node": PoolChange(reviewers=-2)}), 4)
    busier = run(cal, st, Scenario("busier", arrival_multiplier=2.0), 4)
    assert wait(fewer, "sig/node") > wait(base, "sig/node")
    assert busier.total.review_wait_days.median > base.total.review_wait_days.median  # type: ignore[union-attr]


def test_interruptions_lengthen_waits() -> None:
    cal, st = calibration(effort=1.0), state()
    base = run(cal, st, Scenario(), 4)
    busy = run(cal, st, Scenario("busy", {"sig/node": PoolChange(interruption=0.5)}), 4)
    assert wait(busy, "sig/node") > wait(base, "sig/node")


def test_problems_are_reported() -> None:
    bad = Scenario("x", {"sig/nope": PoolChange(), "sig/node": PoolChange(interruption=0.95)}, 5)
    problems = bad.problems(["sig/node", "other"])
    assert any("unknown pool" in p for p in problems)
    assert any("interruption" in p for p in problems)
    assert any("arrival" in p for p in problems)
    assert Scenario().problems(["sig/node"]) == []


def test_calibration_and_scenario_survive_json() -> None:
    cal = calibration()
    assert calibration_from_json(json.loads(json.dumps(calibration_to_json(cal)))) == cal
    s = Scenario("hire", {"sig/node": PoolChange(new_reviewers=2, ramp_weeks=6)}, 1.2)
    assert scenario_from_json(json.loads(json.dumps(scenario_to_json(s)))) == s


def test_current_state_on_the_6395_fixtures() -> None:
    world = project(fixture_events(), utc(2026, 11, 3))
    st = current_state(world, V138, ["sig/api-machinery", "other"])
    # #143709 (opened Nov 2, merged Nov 20) is open on Nov 3.
    main = next(p for p in st.in_flight if p.key == MAIN_PR)
    assert main.opened_at < 0
    assert main.previous_visible <= 0
    assert st.horizon_label == "Code Freeze"
    assert st.horizon_at == utc(2026, 11, 17, 12)


def test_horizon_after_freeze_is_release_day() -> None:
    world = project(fixture_events(), utc(2026, 11, 22))
    assert horizon(world, V138)[1] in {"release day", "4 weeks"}
