"""Run the readiness backtest (#184) and write ``docs/results/readiness-backtest-<ts>.json``.

    python -m modules.readiness.backtest_job

Releases are fixed by ADR-0032: Kubernetes v1.36, v1.37, v1.38 and Kafka 4.4.0. v1.38 counts
for the freeze replay only until it ships (release day Dec 16, 2026).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from opentelemetry import trace

from engine.assess import ReleaseAssessment, assess_release
from engine.projection import project
from modules.readiness.backtest import judge, replay_release

RELEASES = ("kubernetes:v1.36", "kubernetes:v1.37", "kubernetes:v1.38", "KAFKA:4.4.0")
_tracer = trace.get_tracer("modules.readiness.backtest_job")


def main(argv: list[str] | None = None) -> int:
    import argparse

    from sqlalchemy.orm import sessionmaker

    from observability.telemetry import init_telemetry
    from pipeline.store.events_repo import iter_events
    from pipeline.store.session import make_engine

    parser = argparse.ArgumentParser(prog="readiness_backtest")
    parser.add_argument("--out", default="docs/results", help="directory for the result file")
    args = parser.parse_args(argv)
    telemetry = init_telemetry("tpm-readiness-backtest")
    try:
        sessions = sessionmaker(make_engine())
        now = datetime.now(UTC)
        results = []
        for key in RELEASES:
            with sessions() as s:
                events = list(iter_events(s, project=key.split(":", 1)[0]))

            def at(when: datetime, key: str = key, events: list = events) -> ReleaseAssessment:  # type: ignore[type-arg]
                with _tracer.start_as_current_span("readiness.backtest_at"):
                    return assess_release(project(events, when), key)

            results.append(replay_release(key, at, project(events, now)))
        verdict = judge(results)
        body = {
            "result": "readiness_backtest",
            "measured_at": now.isoformat(),
            "releases": [r.as_dict() for r in results],
            "verdict": verdict.as_dict(),
        }
        path = Path(args.out) / f"readiness-backtest-{now:%Y%m%dT%H%M%SZ}.json"
        path.write_text(json.dumps(body, indent=1) + "\n")
        print(json.dumps(body["verdict"]), path)
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        sys.exit(main())
