"""Fit the simulator for a release and store the calibration (ADR-0012).

    make sim-calibrate RELEASE=v1.38                 # Kubernetes (the default project)
    make sim-calibrate RELEASE=KAFKA:4.5.0           # any project: <project>:<release>

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


def release_key(release: str) -> str:
    """``v1.38`` -> ``kubernetes:v1.38``; a ``<project>:<release>`` key is kept as is."""
    return release if ":" in release else f"kubernetes:{release}"


def validation_summary(project: str, results_dir: Path = RESULTS) -> dict[str, Any]:
    """The newest validation run for ``project``, trimmed for display.

    A replay of one project never validates another (ADR-0018): with no run for this
    project, the calibration is stored as not validated and says why.
    """
    for f in sorted(results_dir.glob("sim-validation-*.json"), reverse=True):
        data = json.loads(f.read_text())
        runs = [r for r in data.get("releases", []) if r["release"].split(":", 1)[0] == project]
        if runs:
            return {
                "passed": all(r["passed"] for r in runs),
                "source_file": f.name,
                "measured_at": data.get("measured_at"),
                "tolerance": data.get("tolerance"),
                "releases": [
                    {"release": r["release"], "passed": r["passed"], "checks": r["checks"]}
                    for r in runs
                ],
            }
    return {
        "passed": False,
        "reason": f"no replay validation has been run for {project} yet",
        "releases": [],
    }


def main() -> None:
    """Fit, attach validation, store."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="v1.38", help="v1.38 or <project>:<release>")
    args = parser.parse_args()
    key = release_key(args.release)
    proj = key.split(":", 1)[0]
    engine = make_engine(instrument=False)
    with Session(engine) as session:
        events = list(iter_events(session, project=proj))
    world = project(events, max(e.occurred_at for e in events) + timedelta(seconds=1))
    sources = finished_releases(world, window(world, key).start, exclude=key)
    if not sources:
        raise SystemExit(
            f"No finished {proj} release before {key} to calibrate on: the simulator learns "
            "from earlier releases of the same project (ADR-0012)."
        )
    inputs = measure(world, sources)
    fitted = fit(world, inputs)
    cal = Calibration(
        release_key=key,
        inputs=inputs,
        effort_days=fitted.effort_days,
        scales=fitted.scales,
        validation=validation_summary(proj),
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
