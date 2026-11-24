"""Webhook event -> dashboard latency from Cloud Logging (read-only; P3-M5, ADR-0020).

Reads the receiver's ``webhook received`` lines and the API's ``live update pushed`` lines
through the gcloud CLI, joins them by event ID (``observability/latency.py``) and saves the
per-stage percentiles to ``docs/results``. Pushes only happen to open pages, so keep one
open while activity happens (``curl -N <api>/releases/<name>/stream``)::

    python scripts/measure_webhook_latency.py --hours 24 [--project tpm-intelligence]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from observability.latency import per_event_latency, webhook_latency


def _read(project: str, hours: int, service: str, message: str) -> list[dict[str, Any]]:
    """Payloads of one log line from one Cloud Run service, oldest first."""
    return [payload for _, payload in _read_timed(project, hours, service, message)]


def _read_timed(
    project: str, hours: int, service: str, message: str
) -> list[tuple[datetime, dict[str, Any]]]:
    """(log time, payload) of one log line from one Cloud Run service, oldest first."""
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise SystemExit("gcloud not found on PATH")
    query = (
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="{service}" '
        f'AND jsonPayload.message="{message}"'
    )
    out = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [
            gcloud,
            "logging",
            "read",
            query,
            f"--project={project}",
            f"--freshness={hours}h",
            "--order=asc",
            "--format=json(timestamp,jsonPayload)",
            "--limit=20000",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [
        (
            datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00")),
            dict(row.get("jsonPayload") or {}),
        )
        for row in json.loads(out or "[]")
    ]


def main() -> None:
    """Print and save the per-stage percentiles."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="tpm-intelligence")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--out", default="docs/results")
    args = parser.parse_args()
    receipts = _read_timed(args.project, args.hours, "tpm-webhooks", "webhook received")
    stored = _read_timed(args.project, args.hours, "tpm-api", "event stored")
    pushes = _read_timed(args.project, args.hours, "tpm-api", "live update pushed")
    now = datetime.now(UTC)
    result = {
        "measured_at": now.isoformat(timespec="seconds"),
        "window_hours": args.hours,
        "webhook_deliveries": len(receipts),
        "per_event": per_event_latency(receipts, stored, [at for at, _ in pushes]),
        "per_push": webhook_latency([r for _, r in receipts], [p for _, p in pushes]),
        "note": (
            "per_event (primary): every new webhook event, timed to the first push after it "
            "was stored. per_push: one event per push. total = push - GitHub's occurred_at "
            "(GitHub clock, whole seconds: about +-1 s). Pushes need an open live page."
        ),
    }
    text = json.dumps(result, indent=2)
    print(text)
    out = Path(args.out)
    if out.is_dir():
        (out / f"webhook-latency-cloud-{now:%Y%m%dT%H%M%SZ}.json").write_text(text + "\n")


if __name__ == "__main__":
    main()
