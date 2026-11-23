"""Time one release recompute, stage by stage, on real stored events (read-only; P3-M4).

Two measurements, saved to ``docs/results/recompute-profile-<release>-<UTC stamp>.json``:

* ``stages``: each engine stage on its own, as the service ran them before P3-M4
  (every stage links the release itself), to show where time goes.
* ``service``: the real ``ReleaseService`` path, cold and then after one new event, so
  caching and shared linking show up exactly as the API experiences them.

    DATABASE_URL=... python scripts/profile_recompute.py --release v1.38 [--tag laptop]
"""

from __future__ import annotations

import argparse
import json
import resource
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from api.service import InMemoryEventSource, ReleaseService
from api.validation import Validation
from engine.assess import assess_release
from engine.forecast import DEFAULT_FORECAST, calibrate, finished_releases, forecast_release
from engine.links import link_release
from engine.merge_date import forecast_release_dates
from engine.projection import project
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine


def _lap(out: dict[str, float], name: str, fn: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    result = fn()
    out[name] = round(time.perf_counter() - started, 2)
    return result


def stages(events: list[Any], key: str, now: datetime) -> dict[str, float]:
    """Each stage timed separately (no sharing, no cache)."""
    t: dict[str, float] = {}
    world = _lap(t, "project", lambda: project(events, now))
    _lap(t, "link_release", lambda: link_release(world, key))
    _lap(t, "assess_release", lambda: assess_release(world, key))
    sources = finished_releases(world, now, exclude=key)
    cal = _lap(t, "calibrate", lambda: calibrate(world, sources))
    _lap(t, "forecast_release", lambda: forecast_release(world, key, cal, DEFAULT_FORECAST))
    _lap(t, "merge_dates", lambda: forecast_release_dates(world, key, cal, DEFAULT_FORECAST))
    return t


def service(events: list[Any], name: str, now: datetime) -> dict[str, float]:
    """The API's own recompute: cold, then again after one more event arrives."""
    source = InMemoryEventSource(events[:-1])
    svc = ReleaseService(source, now=lambda: now, validation=lambda: Validation(False, "profile"))
    t: dict[str, float] = {}
    _lap(t, "cold_view", lambda: svc.view(name, wait=True))
    source.events.append(events[-1])  # one new event, as the worker would deliver it
    _lap(t, "view_after_one_new_event", lambda: svc.view(name, wait=True))
    t["calibrations_computed"] = svc.calibrations_computed
    t["new_event_subject"] = events[-1].subject.external_key  # type: ignore[assignment]
    return t


def main() -> None:
    """Print and save the profile."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="v1.38")
    parser.add_argument("--project", default="kubernetes")
    parser.add_argument("--tag", default="laptop", help="where it ran, e.g. laptop or cloud")
    parser.add_argument("--out", default="docs/results")
    parser.add_argument("--skip-stages", action="store_true")
    args = parser.parse_args()
    key = f"{args.project}:{args.release}"
    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session, project=args.project))
    now = datetime.now(UTC)
    result: dict[str, Any] = {
        "measured_at": now.isoformat(timespec="seconds"),
        "tag": args.tag,
        "release": key,
        "events": len(events),
        "note": "single runs, not percentiles",
    }
    if not args.skip_stages:
        result["stages"] = stages(events, key, now)
    result["service"] = service(events, args.release, now)
    # ru_maxrss is KiB on Linux.
    result["max_rss_mib"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    text = json.dumps(result, indent=2)
    print(text)
    out = Path(args.out)
    if out.is_dir():
        name = f"recompute-profile-{args.release}-{args.tag}-{now:%Y%m%dT%H%M%SZ}.json"
        (out / name).write_text(text + "\n")


if __name__ == "__main__":
    main()
