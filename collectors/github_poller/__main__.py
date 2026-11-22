"""Run the GitHub poller once.

    python -m collectors.github_poller --team kubernetes --release v1.38
    python -m collectors.github_poller --team kubernetes --release v1.38 --backfill

Repos and calendar come from ``connectors/teams/<team>.yaml`` so another team can
plug in without editing this module. Exit code 1 if any stream failed.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

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
            logger.error(
                "team %s uses non-GitHub planning; github_poller cannot sync it",
                team.id,
            )
            return 2

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


if __name__ == "__main__":
    sys.exit(main())
