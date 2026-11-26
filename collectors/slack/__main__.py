"""Run the Slack collector once (ADR-0030).

    SLACK_BOT_TOKEN=xoxb-... python -m collectors.slack --team <id> [--since-days 14]

Reads the channels listed under ``conversations`` (``kind: slack_channel``) in
``connectors/teams/<team>.yaml``. The token stays in the environment (Secret Manager in
the cloud), never in config. Exit code 2 if not configured, 1 if a channel failed.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import timedelta

SERVICE_NAME = "tpm-slack-collector"


def main(argv: list[str] | None = None) -> int:
    """Parse args, wire dependencies, collect once."""
    parser = argparse.ArgumentParser(prog="slack")
    parser.add_argument("--team", required=True, help="connectors/teams/<id>.yaml")
    parser.add_argument("--since-days", type=int, default=14)
    args = parser.parse_args(argv)

    from observability.telemetry import init_telemetry

    telemetry = init_telemetry(SERVICE_NAME)
    logger = logging.getLogger("collectors.slack")
    try:
        from collectors.slack.client import SlackClient
        from collectors.slack.sync import collect
        from connectors import load_team
        from pipeline.factory import create_transport
        from pipeline.queue import EventPublisher

        team = load_team(args.team)
        if not any(c.kind == "slack_channel" for c in team.conversations):
            logger.error("team %s lists no Slack channels", team.id)
            return 2
        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            logger.error("SLACK_BOT_TOKEN is not set")
            return 2
        client = SlackClient(token)
        try:
            stats = collect(team, client, EventPublisher(create_transport()),
                            since=timedelta(days=args.since_days))  # fmt: skip
        finally:
            client.close()
        logger.info("slack: %d channels, %d messages, %d events, %d failed",
                    stats.channels, stats.messages, stats.published, len(stats.failed))  # fmt: skip
        return 1 if stats.failed else 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        sys.exit(main())
