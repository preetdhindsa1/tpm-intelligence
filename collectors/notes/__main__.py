"""Run the meeting-notes collector once (ADR-0030).

    python -m collectors.notes --team kubernetes

Reads the publicly shared notes documents listed under ``conversations`` in
``connectors/teams/<team>.yaml``. Set ``GOOGLE_API_KEY`` to read through the Google Drive
API. Exit code 1 if any document failed.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

SERVICE_NAME = "tpm-notes-collector"


def main(argv: list[str] | None = None) -> int:
    """Parse args, wire dependencies, collect once."""
    parser = argparse.ArgumentParser(prog="notes")
    parser.add_argument("--team", default="kubernetes", help="connectors/teams/<id>.yaml")
    args = parser.parse_args(argv)

    from observability.telemetry import init_telemetry

    telemetry = init_telemetry(SERVICE_NAME)
    logger = logging.getLogger("collectors.notes")
    try:
        from collectors.notes.client import NotesClient
        from collectors.notes.sync import collect
        from connectors import load_team
        from pipeline.factory import create_transport
        from pipeline.queue import EventPublisher

        team = load_team(args.team)
        if not team.conversations:
            logger.error("team %s lists no conversation sources", team.id)
            return 2
        client = NotesClient(api_key=os.environ.get("GOOGLE_API_KEY") or None)
        try:
            stats = collect(team, client, EventPublisher(create_transport()))
        finally:
            client.close()
        logger.info(
            "notes: %d documents, %d meetings, %d events, %d failed",
            stats.documents, stats.meetings, stats.published, len(stats.failed),
        )  # fmt: skip
        return 1 if stats.failed else 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
