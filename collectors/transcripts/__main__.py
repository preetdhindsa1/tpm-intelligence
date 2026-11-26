"""Run a meeting-transcript collector once (ADR-0030).

    python -m collectors.transcripts --team <id> --source zoom|teams|meet [--since-days 30]

Credentials come from the environment (Secret Manager in the cloud), never config:
  zoom:  ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
  teams: MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET
  meet:  GOOGLE_MEET_CLIENT_ID, GOOGLE_MEET_CLIENT_SECRET, GOOGLE_MEET_REFRESH_TOKEN
Exit code 2 if not configured, 1 if a source failed.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import timedelta

SERVICE_NAME = "tpm-transcripts-collector"
KIND = {"zoom": "zoom_user", "teams": "teams_organizer", "meet": "google_meet"}
ENV = {
    "zoom": ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"),
    "teams": ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET"),
    "meet": ("GOOGLE_MEET_CLIENT_ID", "GOOGLE_MEET_CLIENT_SECRET", "GOOGLE_MEET_REFRESH_TOKEN"),
}


def main(argv: list[str] | None = None) -> int:
    """Parse args, wire dependencies, collect once."""
    parser = argparse.ArgumentParser(prog="transcripts")
    parser.add_argument("--team", required=True, help="connectors/teams/<id>.yaml")
    parser.add_argument("--source", required=True, choices=sorted(KIND))
    parser.add_argument("--since-days", type=int, default=30)
    args = parser.parse_args(argv)

    from observability.telemetry import init_telemetry

    telemetry = init_telemetry(SERVICE_NAME)
    logger = logging.getLogger("collectors.transcripts")
    try:
        from collectors.transcripts.meet import MeetReader
        from collectors.transcripts.sync import collect
        from collectors.transcripts.teams import TeamsReader
        from collectors.transcripts.zoom import ZoomReader
        from connectors import load_team
        from pipeline.factory import create_transport
        from pipeline.queue import EventPublisher

        team = load_team(args.team)
        kind = KIND[args.source]
        if not any(c.kind == kind for c in team.conversations):
            logger.error("team %s lists no %s sources", team.id, kind)
            return 2
        creds = [os.environ.get(name, "") for name in ENV[args.source]]
        if not all(creds):
            missing = [n for n, v in zip(ENV[args.source], creds, strict=True) if not v]
            logger.error("missing credentials: %s", ", ".join(missing))
            return 2
        a, b, c = creds
        reader: ZoomReader | TeamsReader | MeetReader
        if args.source == "zoom":
            reader = ZoomReader(a, b, c)
        elif args.source == "teams":
            reader = TeamsReader(a, b, c)
        else:
            reader = MeetReader(a, b, c)
        try:
            stats = collect(
                team,
                kind,
                reader,
                EventPublisher(create_transport()),
                since=timedelta(days=args.since_days),
            )
        finally:
            reader.close()
        logger.info(
            "transcripts: %d sources, %d meetings, %d events, %d failed",
            stats.sources,
            stats.meetings,
            stats.published,
            len(stats.failed),
        )
        return 1 if stats.failed else 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        sys.exit(main())
