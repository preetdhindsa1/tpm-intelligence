"""Fit the simulator for a release and store the calibration (ADR-0012).

    make sim-calibrate RELEASE=v1.38

Fits on the releases that finished before ``RELEASE`` started (about 2 minutes), attaches
the newest ``docs/results/sim-validation-*.json`` result, and saves it to
``sim_calibrations``. The API runs scenarios from the newest stored calibration only, so
requests never re-fit.
"""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from api.sim_store import PostgresSimStore
from engine.forecast import finished_releases
from engine.projection import project
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine
from simulator.calibrate import measure, window
from simulator.replay import fit
from simulator.scenario import Calibration

RESULTS = Path(__file__).resolve().parent.parent / "docs" / "results"


def validation_summary(results_dir: Path = RESULTS) -> dict[str, Any]:
    """The newest validation run, trimmed for display. Not validated when there is none."""
    files = sorted(results_dir.glob("sim-validation-*.json"))
    if not files:
        return {"passed": False, "reason": "no validation has been run", "releases": []}
    data = json.loads(files[-1].read_text())
    return {
        "passed": bool(data.get("passed", False)),
        "source_file": files[-1].name,
        "measured_at": data.get("measured_at"),
        "tolerance": data.get("tolerance"),
        "releases": [
            {"release": r["release"], "passed": r["passed"], "checks": r["checks"]}
            for r in data.get("releases", [])
        ],
    }


def main() -> None:
    """Fit, attach validation, store."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="v1.38")
    args = parser.parse_args()
    engine = make_engine(instrument=False)
    with Session(engine) as session:
        events = list(iter_events(session))
    world = project(events, max(e.occurred_at for e in events) + timedelta(seconds=1))
    key = f"kubernetes:{args.release}"
    sources = finished_releases(world, window(world, key).start, exclude=key)
    inputs = measure(world, sources)
    fitted = fit(world, inputs)
    cal = Calibration(
        release_key=key,
        inputs=inputs,
        effort_days=fitted.effort_days,
        scales=fitted.scales,
        validation=validation_summary(),
        data_until=world.as_of,
    )
    row = PostgresSimStore(sessionmaker(engine)).save_calibration(cal)
    print(
        json.dumps(
            {
                "id": row.id,
                "release": key,
                "source_releases": list(sources),
                "effort_days": fitted.effort_days,
                "loss": fitted.loss,
                "validated": cal.validated,
            }
        )
    )


if __name__ == "__main__":
    main()
