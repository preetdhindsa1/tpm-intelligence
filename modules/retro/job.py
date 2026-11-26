"""Compute and store a release's retro (#182): ``python -m modules.retro.job --release KEY``.

Replays the rules day by day from the stored events (ADR-0032 addendum 2), so it takes a few
minutes per release; the API serves the stored run. Confirmed link suggestions are not used:
they were decided later and would leak today's knowledge into the replay.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime

from opentelemetry import trace

from engine.assess import ReleaseAssessment, assess_release
from engine.projection import project
from modules.retro.facts import RetroRun, retro
from pipeline.events import NormalizedEvent

_tracer = trace.get_tracer("modules.retro.job")


def run_release(events: list[NormalizedEvent], release_key: str, now: datetime) -> RetroRun:
    """The retro for one release from its project's events."""

    def replay(day: datetime) -> ReleaseAssessment:
        with _tracer.start_as_current_span("retro.replay_day", attributes={"day": day.isoformat()}):
            return assess_release(project(events, day), release_key)

    with _tracer.start_as_current_span("retro.release", attributes={"release": release_key}):
        return retro(release_key, replay, project(events, now), now)


def main(argv: list[str] | None = None) -> int:
    import argparse

    from sqlalchemy.orm import sessionmaker

    from modules.retro.store import PostgresRetroStore
    from observability.telemetry import init_telemetry
    from pipeline.store.events_repo import iter_events
    from pipeline.store.session import make_engine

    parser = argparse.ArgumentParser(prog="retro_job")
    parser.add_argument("--release", required=True, action="append", help="e.g. kubernetes:v1.37")
    parser.add_argument("--dry-run", action="store_true", help="print, do not store")
    args = parser.parse_args(argv)
    telemetry = init_telemetry("tpm-retro-job")
    try:
        sessions = sessionmaker(make_engine())
        store = PostgresRetroStore(sessions)
        for key in args.release:
            started = time.perf_counter()
            with sessions() as s:
                events = list(iter_events(s, project=key.split(":", 1)[0]))
            run = run_release(events, key, datetime.now(UTC))
            if not args.dry_run:
                store.add(run)
            totals = run.totals()
            print(json.dumps({"release": key, **totals,
                              "seconds": round(time.perf_counter() - started)}))  # fmt: skip
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
