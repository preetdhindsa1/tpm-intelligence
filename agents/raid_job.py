"""Extract RAID suggestions from a release's stored meeting notes (#179).

    python -m agents.raid_job --release kubernetes:v1.38 --workstream K8S

Reads the meetings the notes collector stored (``conversation`` events in the shared
core; never the document itself), masks names, runs the extractor once per meeting and
adds what passes the checks as ``suggested`` RAID items. A re-run costs nothing for
unchanged meetings (gateway cache) and adds no duplicates (suggestion key).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from agents.gateway import AIError, Gateway
from agents.prompts import Prompt
from agents.raid_extractor import Meeting, extract
from modules.raid.mask import mask_names, names_in
from modules.raid.notes import drop_roster, teams_in
from modules.raid.store import RaidStore
from pipeline.store.models import EventRecord

_tracer = trace.get_tracer("agents.raid_job")


def load_meetings(sessions: sessionmaker[Session], release_key: str) -> list[dict[str, Any]]:
    """The latest stored text of each meeting for the release, oldest meeting first."""
    with sessions() as s:
        rows = s.scalars(
            select(EventRecord)
            .where(EventRecord.subject_kind == "conversation")
            .order_by(EventRecord.observed_at)
        ).all()
    latest = {r.subject_key: r.payload for r in rows if r.payload.get("release_key") == release_key}
    return sorted(
        (p for p in latest.values() if p.get("meeting_date")), key=lambda p: p["meeting_date"]
    )


@dataclass
class JobReport:
    """Counts for one run (what goes in ADR-0030)."""

    release_key: str
    meetings: int = 0
    returned: int = 0
    kept: int = 0
    new: int = 0
    by_type: Counter[str] = field(default_factory=Counter)
    dropped: Counter[str] = field(default_factory=Counter)
    with_owner: int = 0
    with_links: int = 0
    unknown_owners: int = 0
    errors: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    cached: int = 0

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready counts."""
        return {**self.__dict__, "by_type": dict(self.by_type), "dropped": dict(self.dropped)}


def run_release(
    gateway: Gateway,
    prompt: Prompt,
    payloads: Sequence[dict[str, Any]],
    release_key: str,
    workstream: str,
    store: RaidStore,
    now: datetime,
    known_names: Iterable[str] = (),
) -> JobReport:
    """Extract every meeting; stops early (keeping what it has) if the budget pauses AI.

    ``known_names`` adds people from the team's public lists to the names found in the notes.
    """
    texts = [drop_roster(p["text"]) for p in payloads]
    names = set(known_names).union(*(names_in(p["text"]) for p in payloads))
    teams = teams_in(mask_names(t, names) for t in texts)
    report = JobReport(release_key)
    with _tracer.start_as_current_span("raid.job", attributes={"raid.release": release_key}):
        for p, text in zip(payloads, texts, strict=True):
            meeting = Meeting(p["container"], release_key, workstream, p["meeting_date"], text)
            try:
                result = extract(gateway, prompt, meeting, names, teams)
            except AIError as exc:
                report.errors.append(f"{p['meeting_date']}: {exc}")
                break
            report.meetings += 1
            report.returned += result.returned
            report.kept += len(result.items)
            report.dropped.update(result.dropped)
            report.unknown_owners += result.unknown_owners
            report.cost_usd += result.cost_usd
            report.cached += result.cached
            for item in result.items:
                report.by_type[item.type] += 1
                report.with_owner += item.owner is not None
                report.with_links += bool(item.links)
                report.new += store.suggest(item, now) is not None
    report.cost_usd = round(report.cost_usd, 6)
    return report


def main(argv: list[str] | None = None) -> int:
    """Run against the database (Postgres ledger and RAID store)."""
    import argparse

    from agents.ledger import PostgresLedger
    from agents.prompts import load_prompt
    from agents.raid_extractor import TASK
    from agents.settings import AISettings
    from collectors.notes.people import fetch_people
    from connectors.load import team_for_project
    from modules.raid.postgres import PostgresRaidStore
    from modules.raid.store import MemoryRaidStore
    from observability.telemetry import init_telemetry
    from pipeline.store.session import make_engine

    parser = argparse.ArgumentParser(prog="raid_job")
    parser.add_argument("--release", required=True, help="e.g. kubernetes:v1.38")
    parser.add_argument("--workstream", required=True, help="RAID ID prefix, e.g. K8S")
    parser.add_argument("--dry-run", action="store_true", help="keep items in memory only")
    args = parser.parse_args(argv)
    telemetry = init_telemetry("tpm-raid-job")
    try:
        sessions = sessionmaker(make_engine())
        gateway = Gateway(AISettings(), PostgresLedger(sessions))
        payloads = load_meetings(sessions, args.release)
        team = team_for_project(args.release.split(":", 1)[0])
        people = fetch_people(team.people_sources) if team else set()
        report = run_release(
            gateway, load_prompt(TASK.name), payloads, args.release, args.workstream,
            MemoryRaidStore() if args.dry_run else PostgresRaidStore(sessions), datetime.now(UTC),
            people,
        )  # fmt: skip
        print(json.dumps(report.as_dict(), indent=1))
        return 1 if report.errors else 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
