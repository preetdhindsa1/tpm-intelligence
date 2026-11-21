"""Run the GitHub poller once.

    python -m collectors.github_poller --release v1.38            # incremental
    python -m collectors.github_poller --release v1.38 --backfill # ignore cursors

Exit code 1 if any stream failed (Cloud Scheduler / Cloud Run jobs then retry and the
"2 failed polls in a row" alert can fire from ``sync_cursors.consecutive_failures``).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

SERVICE_NAME = "tpm-github-poller"


def main(argv: list[str] | None = None) -> int:
    """Parse args, wire dependencies, poll once."""
    parser = argparse.ArgumentParser(prog="github_poller")
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
        from pipeline.factory import create_transport
        from pipeline.queue import EventPublisher
        from pipeline.store.cursors import PostgresCursorStore
        from pipeline.store.session import make_engine

        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            logger.error("GITHUB_TOKEN is not set")
            return 2
        poller = GitHubPoller(
            gh=GitHubClient.from_token(token),
            publisher=EventPublisher(create_transport()),
            cursors=PostgresCursorStore(sessionmaker(make_engine())),
            calendar=load_calendar(),
            release_name=args.release,
        )
        stats = poller.run(backfill=args.backfill)
        return 1 if stats.failed_streams else 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
