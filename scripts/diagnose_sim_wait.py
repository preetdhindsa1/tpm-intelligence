"""Why is the simulated review wait too long? In-sample diagnosis (read-only on the DB).

    python scripts/diagnose_sim_wait.py --release v1.38

Fits exactly as validation does (source releases only), then compares real and simulated
waits **on the source releases** (in-sample). Nothing about the held-out release is used to
choose anything, and no model setting changes. Prints JSON (counts and days, no names).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import timedelta

import numpy as np
from sqlalchemy.orm import Session

from engine.forecast import finished_releases
from engine.projection import project
from engine.review_rounds import review_rounds, review_waits
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine
from simulator.calibrate import days, measure, window, window_prs
from simulator.replay import SEED, fit, replay, staffing

ZERO = 1 / 1440  # one minute, in days


def summary(waits: list[float]) -> dict[str, float | int | None]:
    """Median, quartiles and share of near-zero waits."""
    if not waits:
        return {"n": 0, "median": None}
    q = np.quantile(waits, [0.25, 0.5, 0.75])
    return {
        "n": len(waits),
        "p25": round(float(q[0]), 4),
        "median": round(float(q[1]), 4),
        "p75": round(float(q[2]), 4),
        "share_under_1_min": round(sum(w < ZERO for w in waits) / len(waits), 3),
    }


def real_split(world, w, pools):  # type: ignore[no-untyped-def]
    """Real waits as validation measures them, split by first / later round."""
    first, later, overlapping = [], [], 0
    rounds_per_pr = []
    for pr in window_prs(world, w):
        rounds = [r for r in review_rounds(pr) if r.started_at < w.horizon]
        waits = review_waits(pr, rounds)
        rounds_per_pr.append(len(rounds))
        prev_end = None
        for i, (rnd, x) in enumerate(zip(rounds, waits, strict=True)):
            (first if i == 0 else later).append(days(x))
            if prev_end is not None and rnd.started_at < prev_end:
                overlapping += 1
            prev_end = rnd.ended_at if prev_end is None else max(prev_end, rnd.ended_at)
    return first, later, overlapping, rounds_per_pr


def sim_split(results, horizon):  # type: ignore[no-untyped-def]
    first, later = [], []
    for r in results:
        for i, (at, wait) in enumerate(r.round_waits):
            if at <= horizon:
                (first if i == 0 else later).append(wait)
    return first, later


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="v1.38")
    args = parser.parse_args()
    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session, project="kubernetes"))
    world = project(events, max(e.occurred_at for e in events) + timedelta(seconds=1))
    held = window(world, f"kubernetes:{args.release}")
    sources = finished_releases(world, held.start, exclude=held.release_key)
    inputs = measure(world, sources)
    fitted = fit(world, inputs)
    pools = list(inputs.pools)
    out = {
        "held_out": held.release_key,
        "sources": list(sources),
        "effort_days": fitted.effort_days,
        "scales_at_bounds": sum(
            1 for a, b in fitted.scales.values() for s in (a, b) if s <= 0.011 or s >= 1.99
        ),
        "releases": [],
    }
    for key in sources:
        w = window(world, key)
        first, later, overlapping, rpp = real_split(world, w, pools)
        staff = staffing(world, w, pools)
        horizon = days(w.horizon - w.start)
        sf, sl = [], []
        for rep in range(3):
            res = replay(world, w, inputs, fitted.scales, staff, SEED + 7 * rep, fitted.effort_days)
            a, b = sim_split(res, horizon)
            sf += a
            sl += b
        out["releases"].append(
            {
                "release": key,
                "real": {
                    "all": summary(first + later),
                    "first": summary(first),
                    "later": summary(later),
                    "later_share": round(len(later) / max(1, len(first) + len(later)), 3),
                    "overlapping_rounds": overlapping,
                    "rounds_per_pr": dict(sorted(Counter(min(n, 6) for n in rpp).items())),
                },
                "sim": {
                    "all": summary(sf + sl),
                    "first": summary(sf),
                    "later": summary(sl),
                    "later_share": round(len(sl) / max(1, len(sf) + len(sl)), 3),
                },
            }
        )
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
