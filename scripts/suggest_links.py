"""Run the AI link suggester over a release's unlinked PRs (paid; non-essential).

    make suggest-links RELEASE=v1.38 [LIMIT=100]

Spend counts against the daily cap; the run stops when the budget slows or pauses it, and
the next run continues where it stopped. Suggestions only wait in the review queue
(``/releases/<release>/links``); none counts until a person confirms it.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from agents.gateway import Gateway
from agents.ledger import PostgresLedger
from agents.link_job import suggest_for_release
from agents.link_store import PostgresLinkSuggestionStore, engine_links
from agents.settings import AISettings
from engine.projection import project
from observability.telemetry import init_telemetry
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine


def main() -> None:
    """Print the run report as JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="v1.38")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    key = f"kubernetes:{args.release}"

    telemetry = init_telemetry("tpm-link-suggester")
    try:
        engine = make_engine()
        factory = sessionmaker(engine)
        store = PostgresLinkSuggestionStore(factory)
        with Session(engine) as session:
            events = list(iter_events(session, project="kubernetes"))
        world = project(events, datetime.now(UTC))
        world = replace(world, extra_links=tuple(engine_links(store.list(key))))
        gateway = Gateway(AISettings(), PostgresLedger(factory))
        report = suggest_for_release(
            gateway, store, world, key, limit=args.limit, workers=args.workers
        )
        print(json.dumps(report.as_dict(), indent=1))
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    main()
