"""Real #6395 / #2570 fixtures turned into normalized events via the collector's normalizer."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import cache

from collectors.github_poller import normalize
from collectors.github_poller.calendar import load_calendar
from pipeline.events import NormalizedEvent
from tests.collectors.conftest import load_json, load_text

OBSERVED = datetime(2026, 11, 21, 12, tzinfo=UTC)
ENH = "kubernetes/enhancements"
V138 = "kubernetes:v1.38"
K6395 = f"{ENH}#6395"
K2570 = f"{ENH}#2570"
MAIN_PR = "kubernetes/kubernetes#143709"


def utc(*args: int) -> datetime:
    """Shorthand for an aware UTC datetime."""
    return datetime(*args, tzinfo=UTC)  # type: ignore[misc]


@cache
def fixture_events() -> tuple[NormalizedEvent, ...]:
    """Release, both issues (snapshot + full history), #6395 kep.yaml and its six PRs."""
    events: list[NormalizedEvent] = [
        normalize.release_event("kubernetes", load_calendar().get("v1.38"), OBSERVED)
    ]
    for n in (6395, 2570):
        events.append(
            normalize.issue_snapshot(
                load_json(f"issue_{n}.json"), repo=ENH, project="kubernetes", observed_at=OBSERVED
            )
        )
        events += normalize.issue_history(
            normalize.timeline_to_events(load_json(f"issue_{n}_timeline.json")),
            repo=ENH,
            number=n,
            project="kubernetes",
            observed_at=OBSERVED,
        )
    events.append(
        normalize.kep_spec(
            load_text("kep_6395.yaml"),
            path=load_json("meta.json")["kep_yaml_path"],
            repo=ENH,
            number=6395,
            project="kubernetes",
            observed_at=OBSERVED,
            occurred_at=OBSERVED,
        )
    )
    for node in load_json("prs_6395.json"):
        events += normalize.pull_request_events(node, observed_at=OBSERVED)
    return tuple(events)
