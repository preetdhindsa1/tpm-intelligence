"""Run the engine on stored events and print a summary (read-only).

DATABASE_URL=... python scripts/assess_release.py --release v1.38 [--as-of 2026-11-18T00:00:00Z]
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from engine.assess import assess_release
from engine.projection import project
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine


def main() -> None:
    """Load, project, assess, summarise."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="v1.38")
    parser.add_argument("--as-of", default=None, help="ISO time; default now")
    parser.add_argument("--feature", default="kubernetes/enhancements#6395")
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(UTC)

    t0 = time.perf_counter()
    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session, project="kubernetes"))
    t1 = time.perf_counter()
    world = project(events, as_of)
    t2 = time.perf_counter()
    report = assess_release(world, f"kubernetes:{args.release}")
    t3 = time.perf_counter()

    in_release = [f for f in report.features if f.in_release]
    flags = Counter(flag.code for f in report.features for flag in f.flags)
    feature = next((f for f in report.features if f.key == args.feature), None)
    print(
        json.dumps(
            {
                "as_of": as_of.isoformat(),
                "events": len(events),
                "seconds": {
                    "load": round(t1 - t0, 2),
                    "project": round(t2 - t1, 2),
                    "assess": round(t3 - t2, 2),
                },
                "features_ever_in_release": len(report.features),
                "features_in_release_now": len(in_release),
                "features_with_flags": sum(1 for f in report.features if f.flags),
                "flags_by_code": dict(flags.most_common()),
                "features_with_nonempty_critical_path": sum(
                    1 for f in report.features if f.critical_path
                ),
                "top_unlinked_open_prs_by_sig": report.unlinked_open_prs_by_sig[:5],
                "feature": None
                if feature is None
                else {
                    "key": feature.key,
                    "in_release": feature.in_release,
                    "tracked": feature.tracked,
                    "flags": [f.code for f in feature.flags],
                    "prs": [
                        (p.key, p.state, p.freeze.status.value, p.review_rounds, p.review_records)
                        for p in feature.pull_requests
                    ],
                },
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
