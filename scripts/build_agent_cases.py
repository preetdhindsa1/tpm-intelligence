"""Build golden agent-eval cases from real stored data (read-only on the DB).

    DATABASE_URL=... python scripts/build_agent_cases.py

For v1.37 and v1.38, at 7 days before Code Freeze and 1 day after it, take up to
``--per-point`` at-risk features (most critical flags first, then most warnings, then key)
and store each one's fact sheet exactly as the risk analyst would receive it. Writes
``evals/cases/agent_risk_notes.json``. Uses only data dated before each point.
"""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from agents.selection import critical_flag_keys, feature_facts, is_at_risk
from engine.assess import assess_release
from engine.odds import release_odds
from engine.projection import project
from engine.rules import Severity
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine
from verify.build import OddsFacts, build_fact_sheet

OUT = Path(__file__).resolve().parent.parent / "evals" / "cases" / "agent_risk_notes.json"
POINTS = (("freeze-7d", timedelta(days=-7)), ("freeze+1d", timedelta(days=1)))


def main() -> None:
    """Write the cases file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="append", default=None)
    parser.add_argument("--per-point", type=int, default=3)
    args = parser.parse_args()
    releases = args.release or ["v1.37", "v1.38"]

    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session))
    final = project(events, max(e.occurred_at for e in events) + timedelta(days=1))

    cases = []
    for name in releases:
        key = f"kubernetes:{name}"
        freeze = final.releases[key].code_freeze_at
        if freeze is None:
            raise SystemExit(f"{key} has no Code Freeze date")
        for label, offset in POINTS:
            as_of = freeze + offset
            world = project(events, as_of)
            report = assess_release(world, key)
            odds_run = release_odds(events, key, as_of)
            base = odds_run.recalibration.base_rate
            odds = {
                fc.feature_key: OddsFacts(fc.probability, fc.low, fc.high, base, validated=False)
                for fc in odds_run.forecasts
                if fc.status == "forecast"
            }
            sheet = build_fact_sheet(report, odds)
            at_risk = [f for f in report.features if is_at_risk(f, sheet)]

            def rank(f):  # type: ignore[no-untyped-def]
                crit = sum(fl.severity is Severity.CRITICAL for fl in f.flags)
                warn = sum(fl.severity is Severity.WARNING for fl in f.flags)
                return (-crit, -warn, f.key)

            for f in sorted(at_risk, key=rank)[: args.per_point]:
                cases.append(
                    {
                        "id": f"{name}-{label}-{f.key.rsplit('#', 1)[1]}",
                        "release": key,
                        "as_of": as_of.isoformat(),
                        "feature_key": f.key,
                        "critical_flag_keys": critical_flag_keys(f),
                        "facts": feature_facts(f, sheet).to_records(),
                    }
                )
            print(
                f"{name} {label}: {len(at_risk)} at risk, kept {min(len(at_risk), args.per_point)}"
            )
    OUT.write_text(json.dumps(cases, indent=1, default=str) + "\n")
    print(f"wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
