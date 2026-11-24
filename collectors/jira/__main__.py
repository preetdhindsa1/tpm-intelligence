"""Run the Jira collector once (API only; anonymous reads of public Apache Jira).

    python -m collectors.jira --team kafka --release 4.5.0 [--release 4.4.0] [--backfill]

The Jira site, project key and release-key prefix come from ``connectors/teams/<team>.yaml``.
Exit code 1 if the sync failed.
"""

from __future__ import annotations

import argparse
import logging
import sys

SERVICE_NAME = "tpm-jira-collector"


def main(argv: list[str] | None = None) -> int:
    """Parse args, wire dependencies, sync once."""
    parser = argparse.ArgumentParser(prog="jira")
    parser.add_argument("--team", default="kafka", help="connectors/teams/<id>.yaml")
    parser.add_argument("--release", action="append", required=True, help="e.g. 4.5.0")
    parser.add_argument("--backfill", action="store_true", help="ignore the stored cursor")
    args = parser.parse_args(argv)

    from observability.telemetry import init_telemetry

    telemetry = init_telemetry(SERVICE_NAME)
    logger = logging.getLogger("collectors.jira")
    try:
        from sqlalchemy.orm import sessionmaker

        from collectors.jira.client import JiraClient
        from collectors.jira.sync import JiraCollector
        from connectors import load_team
        from connectors.load import release_plan
        from connectors.schema import JiraPlanning
        from pipeline.factory import create_transport
        from pipeline.queue import EventPublisher
        from pipeline.store.cursors import PostgresCursorStore
        from pipeline.store.session import make_engine

        team = load_team(args.team)
        if not isinstance(team.planning, JiraPlanning):
            logger.error("team %s does not plan in Jira", team.id)
            return 2
        jira = JiraClient.from_base_url(team.planning.base_url)
        try:
            stats = JiraCollector(
                jira=jira,
                publisher=EventPublisher(create_transport()),
                cursors=PostgresCursorStore(sessionmaker(make_engine())),
                project=team.project,
                project_key=team.planning.project_key,
                base_url=team.planning.base_url,
                releases=args.release,
                plan=release_plan(team),
            ).run(backfill=args.backfill)
        finally:
            jira.close()
        return 1 if stats.failed else 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
