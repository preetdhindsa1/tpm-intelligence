"""How fresh a release's data is, from its collectors' last successful syncs (ADR-0036).

The API never calls GitHub or Jira while serving a page, so a slow source cannot slow the
demo. It can only make the data old, and this module says so.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from connectors.schema import GitHubPlanning, JiraPlanning, TeamConfig
from pipeline.store.cursors import StreamHealth

# A source is stale past its threshold: GitHub's polled-data SLO (CLAUDE.md section 9);
# Jira's hourly sync plus 10 minutes (Apache rate limits, CLAUDE.md section 7).
STALE_AFTER = {"github": timedelta(minutes=10), "jira": timedelta(minutes=70)}
# Pollers stop at release day; outcomes are judged 3 days later (engine). After that, old
# data is expected.
FINAL_AFTER = timedelta(days=3)


@dataclass(frozen=True)
class SourceFreshness:
    """One source of a release."""

    kind: str  # planning | code
    system: str  # github | jira
    last_success_at: datetime | None
    age_minutes: float | None
    consecutive_failures: int
    stale: bool


@dataclass(frozen=True)
class Freshness:
    """A release's data age. ``as_of`` is its stalest source's last success."""

    status: str  # fresh | stale | final | unknown
    as_of: datetime | None
    sources: tuple[SourceFreshness, ...]


def _source(team: TeamConfig, stream: str, release: str) -> tuple[str, str] | None:
    """(kind, system) if ``stream`` is one of this team's streams for ``release``."""
    parts = stream.split(":")
    if len(parts) < 4:
        return None
    system, owner, what, releases = parts[0], parts[1], parts[2], ":".join(parts[3:])
    if release not in releases.split("+"):
        return None
    planning = team.planning
    if system == "jira":
        if isinstance(planning, JiraPlanning) and owner == planning.project_key:
            return ("planning", "jira")
        return None
    if system != "github":
        return None
    if what == "issues" and isinstance(planning, GitHubPlanning) and owner == planning.repo:
        return ("planning", "github")
    if what == "prs" and owner in team.code.repos:
        return ("code", "github")
    return None


def release_freshness(
    team: TeamConfig,
    release: str,
    release_at: datetime | None,
    streams: Iterable[StreamHealth],
    now: datetime,
) -> Freshness:
    """Freshness of one release of ``team`` at ``now`` (ADR-0036 section 2)."""
    sources = []
    for s in streams:
        src = _source(team, s.stream, release)
        if src is None:
            continue
        kind, system = src
        age = None if s.last_success_at is None else now - s.last_success_at
        stale = age is None or age > STALE_AFTER[system]
        minutes = None if age is None else round(age.total_seconds() / 60, 1)
        sources.append(SourceFreshness(kind, system, s.last_success_at, minutes,
                                       s.consecutive_failures, stale))  # fmt: skip
    sources.sort(key=lambda x: (x.kind != "planning", x.system))
    if not sources:
        return Freshness("unknown", None, ())
    successes = [x.last_success_at for x in sources]
    as_of = None if None in successes else min(x for x in successes if x is not None)
    if release_at is not None and now > release_at + FINAL_AFTER:
        status = "final"
    elif any(x.stale for x in sources):
        status = "stale"
    else:
        status = "fresh"
    return Freshness(status, as_of, tuple(sources))
