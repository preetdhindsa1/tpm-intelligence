"""Readiness on real data (#181): the rules over the release view, and the decision log.

``modules.readiness.rules`` computes every criterion. This layer adds links, the team's
configured criteria, and the append-only log. Logins never leave it: decisions show the role.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any

from opentelemetry import trace

from api.validation import Validation, load_readiness_validation
from connectors.load import load_teams
from modules.raid.store import RaidItem
from modules.readiness.decisions import Decision, DecisionLog
from modules.readiness.rules import NAMES, Criterion, Readiness, evaluate

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
_GITHUB = re.compile(r"^(feature|pr):([\w.-]+/[\w.-]+)#(\d+)$")


def evidence_url(ref: str) -> str | None:
    """A GitHub link for a feature issue or a PR ref; None for anything else."""
    m = _GITHUB.match(ref)
    if not m:
        return None
    kind, repo, n = m.groups()
    return f"https://github.com/{repo}/{'pull' if kind == 'pr' else 'issues'}/{n}"


def _criterion(c: Criterion) -> dict[str, Any]:
    ev = [{"text": e.text, "ref": e.ref, "url": evidence_url(e.ref)} for e in c.evidence]
    return {"id": c.id, "name": c.name, "status": c.status, "detail": c.detail,
            "count": c.count, "evidence": ev}  # fmt: skip


def _decision(d: Decision) -> dict[str, Any]:
    return {"decision": d.decision, "note": d.note, "decided_by": "approver",
            "decided_at": d.decided_at, "facts_as_of": d.facts_as_of}  # fmt: skip


class StoreReadiness:
    """``/readiness`` from the release view, confirmed RAID items and the decision log."""

    synthetic = False

    def __init__(
        self,
        view: Callable[[str], Awaitable[Any]],  # release name -> ReleaseView (404 if unknown)
        raid: Callable[[str], Sequence[RaidItem]],
        log: DecisionLog,
        validation: Validation | None = None,
    ) -> None:
        self._view, self._raid, self._log = view, raid, log
        self._validation = validation or load_readiness_validation()

    def _items(self, release_key: str) -> list[RaidItem] | None:
        try:
            return list(self._raid(release_key))
        except Exception:  # a RAID outage must not read as "no risks"
            logger.warning("RAID items unavailable for %s", release_key, exc_info=True)
            return None

    async def evaluate(self, release: str) -> Readiness:
        view = await self._view(release)
        key = view.assessment.release.key
        project = key.split(":", 1)[0]
        team = next((t for t in load_teams().values() if t.project == project), None)
        config = team.readiness if team else None
        criteria = config.criteria if config else tuple(NAMES)
        with tracer.start_as_current_span("readiness.evaluate", attributes={"release": key}):
            items = self._items(key)
            result = evaluate(view.assessment, items or [], criteria,
                              config.docs_repos if config else ())  # fmt: skip
        if items is None and "risks_owned" in criteria:
            down = Criterion("risks_owned", NAMES["risks_owned"], "unknown",
                             "RAID items could not be read.", None)  # fmt: skip
            rows = tuple(down if c.id == "risks_owned" else c for c in result.criteria)
            result = replace(result, criteria=rows)
        return result

    def out(self, r: Readiness) -> dict[str, Any]:
        """The contract's ``ReadinessOut`` body."""
        project, name = r.release_key.split(":", 1)
        return {
            "project": project, "release": name, "as_of": r.as_of, "synthetic": False,
            "verdict": r.verdict, "criteria": [_criterion(c) for c in r.criteria],
            "decisions": [_decision(d) for d in self._log.list(r.release_key)],
            "summary": None, "validated": self._validation.validated,
            "validation_note": self._validation.reason,
        }  # fmt: skip

    async def readiness(self, release: str) -> dict[str, Any]:
        return self.out(await self.evaluate(release))

    async def decide(self, release: str, decision: str, note: str, by: str,
                     at: datetime) -> dict[str, Any]:  # fmt: skip
        """Append the call with the facts the person saw (as of now), then return the view."""
        r = await self.evaluate(release)
        self._log.append(Decision(r.release_key, decision, note, at, r.as_of,  # type: ignore[arg-type]
                                  r.verdict, by))  # fmt: skip
        return self.out(r)
