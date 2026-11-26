"""Backtest merge-date forecasts on finished releases (read-only on the DB). ADR-0005.

    DATABASE_URL=... python scripts/run_date_backtest.py --release v1.35 ... --release v1.38

Writes docs/results/date-backtest-<UTC timestamp>.json and prints a summary.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from engine.backtest_dates import backtest_dates
from engine.forecast import ForecastConfig
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine

OUT = Path(__file__).resolve().parent.parent / "docs" / "results"


def main() -> None:
    """Load events once, backtest each release, save and print results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="append", required=True)
    parser.add_argument("--lead", type=int, action="append", default=None)
    parser.add_argument("--replications", type=int, default=20)
    parser.add_argument("--sims", type=int, default=500)
    parser.add_argument("--durations", choices=["all", "main"], default="all")
    parser.add_argument("--tag", default="", help="suffix for the results file name")
    args = parser.parse_args()
    leads = args.lead or [28, 14, 7, -3]
    config = ForecastConfig(
        replications=args.replications, sims=args.sims, durations=args.durations
    )

    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session, project="kubernetes"))
    started = time.perf_counter()
    results = [
        r
        for name in args.release
        for r in backtest_dates(events, f"kubernetes:{name}", leads, config)
    ]
    elapsed = round(time.perf_counter() - started, 1)
    validated = bool(results) and all(r.passes for r in results)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"date-backtest-{stamp}{'-' + args.tag if args.tag else ''}.json"
    payload = {
        "measured_at": stamp,
        "events": len(events),
        "seconds": elapsed,
        "config": asdict(config),
        "validated": validated,
        "rule": "every release and lead: 10th-90th coverage in [0.70, 0.90] and CRPS skill > 0",
        "results": [asdict(r) for r in results],
    }
    path.write_text(json.dumps(payload, indent=1, default=str) + "\n")
    summary = [{k: v for k, v in asdict(r).items() if k != "cases"} for r in results]
    print(
        json.dumps(
            {
                "file": str(path.relative_to(OUT.parent.parent)),
                "seconds": elapsed,
                "validated": validated,
                "summary": summary,
            },
            indent=1,
            default=str,
        )
    )


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        main()
