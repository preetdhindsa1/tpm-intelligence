"""Event -> dashboard latency from the API's logs (read-only; P3-M4, ADR-0019).

Reads ``live update pushed`` and ``release view computed`` lines from Cloud Logging
through the gcloud CLI and reports percentiles. Latency per push is the measured
``seconds_since_notified`` plus the hub's batching delay (``debounce_s``, an upper
bound), so the reported figure errs high::

    python scripts/measure_freshness.py --hours 3 [--project tpm-intelligence]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np


def _read(project: str, hours: int, message: str) -> list[dict[str, object]]:
    query = (
        'resource.type="cloud_run_revision" AND resource.labels.service_name="tpm-api" '
        f'AND jsonPayload.message="{message}"'
    )
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise SystemExit("gcloud not found on PATH")
    out = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [
            gcloud,
            "logging",
            "read",
            query,
            f"--project={project}",
            f"--freshness={hours}h",
            "--format=json(timestamp,jsonPayload)",
            "--limit=5000",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rows: list[dict[str, object]] = json.loads(out or "[]")
    return rows


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    a = np.array(values)
    return {
        "n": len(values),
        "p50": round(float(np.percentile(a, 50)), 2),
        "p95": round(float(np.percentile(a, 95)), 2),
        "max": round(float(a.max()), 2),
    }


def main() -> None:
    """Print and save the percentiles."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="tpm-intelligence")
    parser.add_argument("--hours", type=int, default=3)
    parser.add_argument("--release", default="kubernetes:v1.38")
    parser.add_argument("--out", default="docs/results")
    args = parser.parse_args()
    pushes = _read(args.project, args.hours, "live update pushed")
    views = _read(args.project, args.hours, "release view computed")
    latency = [
        float(p["jsonPayload"]["seconds_since_notified"]) + float(p["jsonPayload"]["debounce_s"])  # type: ignore[index]
        for p in pushes
    ]
    recompute = [
        float(v["jsonPayload"]["seconds"])  # type: ignore[index]
        for v in views
        if v["jsonPayload"].get("release") == args.release  # type: ignore[union-attr]
    ]
    now = datetime.now(UTC)
    result = {
        "measured_at": now.isoformat(timespec="seconds"),
        "window_hours": args.hours,
        "event_to_dashboard_seconds": _summary(latency),
        "note": "seconds_since_notified + debounce_s (upper bound); pushes need an open live page",
        f"recompute_seconds_{args.release}": _summary(recompute),
    }
    text = json.dumps(result, indent=2)
    print(text)
    out = Path(args.out)
    if out.is_dir():
        (out / f"freshness-cloud-{now:%Y%m%dT%H%M%SZ}.json").write_text(text + "\n")


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        main()
