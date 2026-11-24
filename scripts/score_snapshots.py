"""Score a finished release on the forecasts recorded while it ran (ADR-0015).

    DATABASE_URL=... python scripts/score_snapshots.py --release v1.39 [--model-version ...]

This is the unseen test: the snapshots were stored, append-only, before the outcome
existed. Scores use the same rules as the backtests (ADR-0005), fixed in ADR-0015:
- odds at 28/14/7 days before Code Freeze: validated if Brier skill against the recorded
  base rate is above 0 at every lead time;
- merge dates at 28/14/7 days before and 3 after: validated if coverage of the 10th-90th
  range is 70-90% and CRPS skill against the baseline is above 0 at every lead time.
Writes docs/results/snapshot-score-<release>-<UTC timestamp>.json.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from api.snapshots import PostgresSnapshotStore, pick, score_merge_dates, score_odds
from engine.backtest_dates import actual_day, baseline_days
from engine.forecast import finished_releases, landed, model_version, outcome_cutoff
from engine.merge_date import TAIL, grid
from engine.projection import project
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine

OUT = Path(__file__).resolve().parent.parent / "docs" / "results"


def main() -> None:
    """Load the release's snapshots and events, score each lead time, save the result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--model-version", default=None, help="default: the current model")
    args = parser.parse_args()
    key = f"kubernetes:{args.release}"
    version = args.model_version or model_version()

    engine = make_engine(instrument=False)
    with Session(engine) as session:
        events = list(iter_events(session, project="kubernetes"))
    latest = max(e.occurred_at for e in events)
    final = project(events, latest + timedelta(days=1))
    release = final.releases[key]
    if release.code_freeze_at is None or release.release_at is None:
        raise SystemExit(f"{key} has no Code Freeze or release date")
    if latest < release.release_at + TAIL:
        raise SystemExit(
            f"{key} cannot be scored yet: wait until {release.release_at + TAIL:%Y-%m-%d}"
        )
    runs = PostgresSnapshotStore(sessionmaker(engine)).runs(key, version)
    cutoff = outcome_cutoff(release)
    if cutoff is None:
        raise SystemExit(f"{key} has no outcome date")
    truth = project(events, cutoff + timedelta(seconds=1))

    odds = []
    for lead in (28, 14, 7):
        run = pick(runs, release.code_freeze_at, lead)
        if run is None:
            odds.append({"lead_days": lead, "missing": True})
            continue
        outcomes = {
            k: bool(landed(f, release))
            for k, f in truth.features.items()
            if landed(f, release) is not None
        }
        odds.append(asdict(score_odds(run, outcomes, lead)))

    dates = []
    for lead in (28, 14, 7, -3):
        run = pick(runs, release.code_freeze_at, lead)
        if run is None:
            dates.append({"lead_days": lead, "missing": True})
            continue
        horizon = grid(release, run.as_of)[-1]
        actual = {
            f.feature_key: actual_day(final, release, f.feature_key, horizon) for f in run.features
        }
        world = project(events, run.as_of)
        base = baseline_days(
            events, world, finished_releases(world, run.as_of, exclude=key), float(lead)
        )
        dates.append(asdict(score_merge_dates(run, actual, base, lead)))

    odds_ok = all(not r.get("missing") and (r.get("skill") or 0) > 0 for r in odds)
    dates_ok = all(
        not r.get("missing")
        and r.get("coverage") is not None
        and 0.70 <= r["coverage"] <= 0.90
        and (r.get("crps_skill") or 0) > 0
        for r in dates
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "release": key,
        "model_version": version,
        "snapshots": len(runs),
        "odds": odds,
        "odds_validated": odds_ok,
        "merge_dates": dates,
        "merge_dates_validated": dates_ok,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"snapshot-score-{args.release}-{stamp}.json"
    path.write_text(json.dumps(payload, indent=1, default=str) + "\n")
    print(json.dumps({"file": str(path.name), **payload}, indent=1, default=str))


if __name__ == "__main__":
    main()
