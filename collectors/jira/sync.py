"""Sync a team's Jira plan for some releases into normalized events (ADR-0018, draft).

Issues are found by fix version, including issues that **used to** carry it: CLAUDE.md
section 6 says removed items disappear from current-state searches, and a feature
dropped from a release must still show as removed. Incremental by ``updated`` with a
one-day overlap (JQL dates are minute-precision and use the server's time zone); event
IDs are deterministic, so overlap re-publishes duplicates that the worker ignores.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from opentelemetry import trace

from collectors.github_poller.calendar import ReleaseDates
from collectors.jira import normalize
from collectors.jira.client import JiraClient
from pipeline.events import NormalizedEvent
from pipeline.queue import EventPublisher
from pipeline.store.cursors import CursorStore

logger = logging.getLogger("collectors.jira")
tracer = trace.get_tracer(__name__)

OVERLAP = timedelta(days=1)


@dataclass
class JiraStats:
    """What one run did."""

    issues: int = 0
    full_changelogs_fetched: int = 0
    remote_link_calls: int = 0
    events_published: int = 0
    failed: bool = False


@dataclass
class JiraCollector:
    """Syncs one Jira project for the given releases. Construct per run."""

    jira: JiraClient
    publisher: EventPublisher
    cursors: CursorStore
    project: str  # release-key prefix, e.g. "KAFKA" -> "KAFKA:4.5.0"
    project_key: str  # Jira project key
    base_url: str
    releases: Sequence[str]
    # Hand-entered freeze dates per release name (the team's calendar file, #8).
    plan: Mapping[str, ReleaseDates] = field(default_factory=dict)
    landed_at: str = "code_freeze"
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    stats: JiraStats = field(default_factory=JiraStats)

    @property
    def stream(self) -> str:
        """Cursor key."""
        return f"jira:{self.project_key}:issues:{'+'.join(sorted(self.releases))}"

    def jql(self, since: datetime | None) -> str:
        """Issues that carry, or once carried, one of the releases as a fix version."""
        versions = ", ".join(f'"{v}"' for v in sorted(self.releases))
        query = (
            f"project = {self.project_key} AND "
            f"(fixVersion in ({versions}) OR fixVersion was in ({versions}))"
        )
        if since is not None:
            query += f' AND updated >= "{(since - OVERLAP):%Y/%m/%d %H:%M}"'
        return query + " ORDER BY updated ASC"

    def run(self, *, backfill: bool = False) -> JiraStats:
        """Sync once; on failure keep the cursor and count it."""
        started = self.now()
        cursor = None if backfill else self.cursors.get(self.stream)
        since = datetime.fromisoformat(cursor) if cursor else None
        with tracer.start_as_current_span(
            "jira.run",
            attributes={"tpm.releases": ",".join(self.releases), "tpm.backfill": backfill},
        ):
            try:
                newest = self._sync(since)
            except Exception as exc:
                self.stats.failed = True
                failures = self.cursors.record_failure(
                    self.stream, f"{type(exc).__name__}: {exc}", started
                )
                logger.exception("jira sync failed", extra={"consecutive_failures": failures})
                return self.stats
        self.cursors.record_success(self.stream, newest.isoformat() if newest else cursor, started)
        logger.info("jira sync finished", extra={"stats": self.stats.__dict__})
        return self.stats

    def _sync(self, since: datetime | None) -> datetime | None:
        observed = self.now()
        newest: datetime | None = since
        before = self.jira.full_changelogs
        # Release dates from Jira versions (ADR-0018). Deterministic IDs, so re-runs
        # publish duplicates the worker ignores; a changed date is a new event.
        for event in normalize.release_events(
            self.jira.versions(self.project_key),
            self.releases,
            project=self.project,
            project_key=self.project_key,
            base_url=self.base_url,
            observed_at=observed,
            plan=self.plan,
            landed_at=self.landed_at,
        ):
            self.publisher.publish(event)
            self.stats.events_published += 1
        for issue in self.jira.search(self.jql(since)):
            self.stats.issues += 1
            key = issue["key"]
            events: list[NormalizedEvent] = [
                normalize.issue_snapshot(
                    issue, project=self.project, base_url=self.base_url, observed_at=observed
                ),
                *normalize.issue_history(issue, project=self.project, observed_at=observed),
            ]
            self.stats.remote_link_calls += 1
            links = self.jira.remote_links(key)
            events += normalize.remote_link_events(key, links, observed_at=observed)
            spec = normalize.issue_spec(issue, links, observed_at=observed)
            if spec is not None:
                events.append(spec)
            for event in events:
                self.publisher.publish(event)
                self.stats.events_published += 1
            updated = normalize.parse_ts(issue["fields"]["updated"])
            newest = updated if newest is None or updated > newest else newest
        self.stats.full_changelogs_fetched = self.jira.full_changelogs - before
        return newest
