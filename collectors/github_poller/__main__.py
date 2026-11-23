"""Run the GitHub poller once.

    python -m collectors.github_poller --team kubernetes --release v1.38
    python -m collectors.github_poller --team kubernetes --release v1.38 --backfill
    python -m collectors.github_poller --team kafka --release 4.4.0 --backfill

For a team that plans in Jira (Kafka, ADR-0018) only the code repo's PRs are synced,
over the window the Jira version dates give (previous x.y.0 release to this release, or
now while the release date is unset).

Repos and calendar come from ``connectors/teams/<team>.yaml`` so another team can
plug in without editing this module. Exit code 1 if any stream failed.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SERVICE_NAME = "tpm-github-poller"


def main(argv: list[str] | None = None) -> int:
    """Parse args, wire dependencies, poll once."""
    parser = argparse.ArgumentParser(prog="github_poller")
    parser.add_argument(
        "--team",
        default="kubernetes",
        help="connectors/teams/<id>.yaml (default: kubernetes)",
    )
    parser.add_argument("--release", required=True, help="e.g. v1.38")
    parser.add_argument("--backfill", action="store_true", help="ignore stored cursors")
    args = parser.parse_args(argv)

    from observability.telemetry import init_telemetry

    telemetry = init_telemetry(SERVICE_NAME)
    logger = logging.getLogger("collectors.github_poller")
    try:
        from sqlalchemy.orm import sessionmaker

        from collectors.github_poller.calendar import load_calendar
        from collectors.github_poller.client import GitHubClient
        from collectors.github_poller.sync import GitHubPoller
        from connectors import load_team
        from pipeline.env import configured
        from pipeline.factory import create_transport
        from pipeline.queue import EventPublisher
        from pipeline.store.cursors import PostgresCursorStore
        from pipeline.store.session import make_engine

        token = configured("GITHUB_TOKEN")
        if not token:
            logger.error("GITHUB_TOKEN is not set (or still the deploy placeholder)")
            return 2

        team = load_team(args.team)
        if team.planning_repo is None:
            window = _jira_window(team, args.release)
            if window is None:
                logger.error("release %s has no cycle start in Jira", args.release)
                return 2
            poller = GitHubPoller(
                gh=GitHubClient.from_token(token),
                publisher=EventPublisher(create_transport()),
                cursors=PostgresCursorStore(sessionmaker(make_engine())),
                calendar=None,
                release_name=args.release,
                enhancements_repo=None,
                code_repo=team.primary_code_repo,
                window=window,
            )
            logger.info(
                "code-only poll of %s for %s: %s", team.primary_code_repo, args.release, window
            )
            stats = poller.run(backfill=args.backfill)
            return 1 if stats.failed_streams else 0

        calendar = load_calendar(team.calendar_path(relative_to=Path.cwd()))
        logger.info(
            "polling team %s planning=%s code=%s link_pack=%s release=%s",
            team.id,
            team.planning_repo,
            team.primary_code_repo,
            team.link_pack,
            args.release,
        )
        poller = GitHubPoller(
            gh=GitHubClient.from_token(token),
            publisher=EventPublisher(create_transport()),
            cursors=PostgresCursorStore(sessionmaker(make_engine())),
            calendar=calendar,
            release_name=args.release,
            enhancements_repo=team.planning_repo,
            code_repo=team.primary_code_repo,
        )
        stats = poller.run(backfill=args.backfill)
        return 1 if stats.failed_streams else 0
    finally:
        telemetry.shutdown()


def _jira_window(team: Any, release: str) -> tuple[datetime, datetime | None] | None:
    """(cycle start, release day) for a Jira-planned release, from its Jira versions."""
    from collectors.jira import normalize
    from collectors.jira.client import JiraClient
    from connectors.schema import JiraPlanning

    planning = team.planning
    if not isinstance(planning, JiraPlanning):
        return None
    jira = JiraClient.from_base_url(planning.base_url)
    try:
        versions = jira.versions(planning.project_key)
    finally:
        jira.close()
    events = normalize.release_events(
        versions,
        [release],
        project=team.project,
        project_key=planning.project_key,
        base_url=planning.base_url,
        observed_at=datetime.now(UTC),
    )
    if not events:
        return None
    payload = events[0].payload
    start = getattr(payload, "cycle_start_at", None)
    return (start, getattr(payload, "release_at", None)) if start else None


if __name__ == "__main__":
    sys.exit(main())
