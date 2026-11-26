"""Retros on real data (#182): stored runs (modules/retro/job.py) and RAID items.

Every number comes from the stored replay; the API only reshapes it. Patterns are per
pool with a minimum group of 10, never per person.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from modules.raid.store import RaidItem
from modules.retro.facts import MIN_GROUP, RetroRun, patterns, same_day
from modules.retro.store import RetroStore

SOURCE = {
    "kind": "snapshots",
    "title": "Rule flags replayed as of each day from stored events (ADR-0032)",
    "url": None,
    "synthetic": False,
}


def public_retros(project: str, release: str) -> list[dict[str, Any]]:
    """The team's public retrospective documents for the release (``layout: retro``)."""
    from connectors.load import load_teams
    from connectors.schema import GoogleDocSource

    return [
        {"kind": "retro", "title": c.title, "synthetic": False,
         "url": f"https://docs.google.com/document/d/{c.document_id}"}
        for t in load_teams().values() if t.project == project
        for c in t.conversations
        if isinstance(c, GoogleDocSource) and c.layout == "retro" and c.release == release
    ]  # fmt: skip


class StoreRetro:
    synthetic = False

    def __init__(self, store: Callable[[], RetroStore],
                 raid: Callable[[str], Sequence[RaidItem]]) -> None:  # fmt: skip
        self._store, self._raid = store, raid

    def _run(self, project: str, release: str) -> RetroRun:
        run = self._store().latest(f"{project}:{release}")
        if run is None:
            raise HTTPException(404, f"no retro computed for {project} {release}")
        return run

    def retro(self, project: str, release: str) -> dict[str, Any]:
        run = self._run(project, release)
        docs = public_retros(project, release)
        name = f"{project.capitalize()} {release}"
        return {
            "project": project, "release": release,
            "label": f"{name}, public retro" if docs else f"{name}, replayed retro",
            "as_of": run.computed_at, "synthetic": False, "sources": [*docs, SOURCE],
            "totals": run.totals(),
            "slips": [{**s.__dict__} for s in run.slips],
        }  # fmt: skip

    def said_vs_showed(self, project: str, release: str) -> dict[str, Any]:
        run = self._run(project, release)
        by_date: dict[str, list[RaidItem]] = defaultdict(list)
        for i in self._raid(run.release_key):
            by_date[i.meeting_date].append(i)
        rows = []
        for date in sorted(by_date):
            at = datetime.fromisoformat(date).replace(hour=12, tzinfo=UTC)
            day = same_day(run.days, at)
            showed = [] if day is None else [
                {"name": "in_release", "value": day.in_release},
                {"name": "features_at_risk", "value": day.features_at_risk},
                {"name": "critical_flags", "value": day.critical_flags},
                {"name": "replay_day", "value": day.at.date().isoformat()},
            ]  # fmt: skip
            said = [{"item_id": i.item_id, "raid_id": i.raid_id, "type": i.type,
                     "title": i.title, "review": i.review} for i in by_date[date]]  # fmt: skip
            rows.append({"date": at, "said": said, "showed": showed})
        return {"project": project, "release": release, "synthetic": False, "rows": rows}

    def patterns(self, project: str) -> dict[str, Any]:
        runs = [r for r in self._store().latest_all() if r.release_key.startswith(f"{project}:")]
        shown, suppressed = patterns(runs)
        rows = [{**p.__dict__, "releases": list(p.releases)} for p in shown]
        return {"project": project, "synthetic": False, "min_group": MIN_GROUP,
                "suppressed_groups": suppressed, "patterns": rows}  # fmt: skip
