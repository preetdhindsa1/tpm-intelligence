"""Validate the simulator by replaying v1.37 and v1.38 (read-only on the DB).

    make sim-validate

For each release: fit on releases finished before it started, replay it with its real
arrivals and staffing, and compare median review wait and median time to merge with the
real values (±20%). Writes ``docs/results/sim-validation-<stamp>.json``; the API shows the
simulator as "not validated" unless the newest file passed for every release.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from engine.projection import project
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine
from simulator.replay import TOLERANCE, validate

OUT = Path(__file__).resolve().parent.parent / "docs" / "results"


def main() -> None:
    """Print and save the validation report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="append", default=None)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session, project="kubernetes"))
    world = project(events, max(e.occurred_at for e in events) + timedelta(seconds=1))
    results = []
    for name in args.release or ["v1.37", "v1.38"]:
        started = time.perf_counter()
        v = validate(world, f"kubernetes:{name}")
        results.append(
            {
                "release": v.release_key,
                "passed": v.passed,
                "source_releases": list(v.source_releases),
                "replications": v.replications,
                "checks": [{**asdict(c), "error": c.error, "passed": c.passed} for c in v.checks],
                "work_scale_fitted": dict(v.service_days),
                "reviewers_per_week": dict(v.staffing),
                "effort_days": v.effort_days,
                "seconds": round(time.perf_counter() - started, 1),
            }
        )
    report = {
        "suite": "simulator_validation",
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_until": world.as_of.isoformat(timespec="seconds"),
        "tolerance": TOLERANCE,
        "passed": all(r["passed"] for r in results),
        "releases": results,
    }
    text = json.dumps(report, indent=1)
    print(text)
    if not args.no_save:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        (OUT / f"sim-validation-{stamp}.json").write_text(text + "\n")


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        main()
