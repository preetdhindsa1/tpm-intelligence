"""Record today's forecast of the current release (append-only; ADR-0015).

    DATABASE_URL=... python scripts/snapshot_forecasts.py [--release v1.38]

The API records a snapshot automatically when it computes the current release; this is the
same step on demand (or from a scheduler). It never overwrites: one run per release, day
and model version.
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy.orm import sessionmaker

from api.service import PostgresEventSource, ReleaseService
from api.snapshots import PostgresSnapshotStore, build_snapshot, worth_recording
from engine.forecast import model_version
from pipeline.store.session import make_engine


def main() -> None:
    """Compute the release view and store its snapshot if today's is missing."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default=None, help="default: the current release")
    args = parser.parse_args()
    factory = sessionmaker(make_engine(instrument=False))
    service = ReleaseService(PostgresEventSource(factory))
    name = args.release or service.current_release_name()
    if name is None:
        raise SystemExit("no release data")
    run = build_snapshot(service.view(name))
    store = PostgresSnapshotStore(factory)
    if not worth_recording(run):
        result = "skipped: release finished"
    else:
        result = "stored" if store.save(run) is not None else "already recorded today"
    print(
        json.dumps(
            {
                "release": run.release_key,
                "date": str(run.snapshot_date),
                "model_version": model_version(),
                "features": len(run.features),
                "result": result,
            }
        )
    )


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        main()
