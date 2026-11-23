"""Backtest the forecast on finished releases using stored events (read-only on the DB).

    DATABASE_URL=... python scripts/run_backtest.py --release v1.37 --release v1.38

Writes docs/results/backtest-<UTC timestamp>.json and prints a summary.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from engine.backtest import backtest
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
    parser.add_argument("--required-prs", choices=["main", "all"], default="main")
    parser.add_argument("--durations", choices=["all", "main"], default="all")
    parser.add_argument("--non-code-removal", action="store_true")
    parser.add_argument("--tag", default="", help="suffix for the results file name")
    args = parser.parse_args()
    leads = args.lead or [28, 14, 7]
    config = ForecastConfig(
        replications=args.replications,
        sims=args.sims,
        required_prs=args.required_prs,
        durations=args.durations,
        non_code_removal=args.non_code_removal,
    )

    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session, project="kubernetes"))
    started = time.perf_counter()
    results = [
        r for name in args.release for r in backtest(events, f"kubernetes:{name}", leads, config)
    ]
    elapsed = round(time.perf_counter() - started, 1)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"backtest-{stamp}{'-' + args.tag if args.tag else ''}.json"
    path.write_text(
        json.dumps(
            {
                "measured_at": stamp,
                "events": len(events),
                "seconds": elapsed,
                "config": asdict(config),
                "results": [asdict(r) for r in results],
            },
            indent=1,
            default=str,
        )
        + "\n"
    )
    summary = [{k: v for k, v in asdict(r).items() if k != "cases"} for r in results]
    print(
        json.dumps(
            {
                "file": str(path.relative_to(OUT.parent.parent)),
                "seconds": elapsed,
                "summary": summary,
            },
            indent=1,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
