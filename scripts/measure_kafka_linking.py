"""Measure linking coverage for one Kafka release on real data (read-only; ADR-0018).

Runs the same engine the API runs (Kafka world only, jira_key pack plus remote links and
sub-task roll-up) and saves the numbers to ``docs/results``::

    DATABASE_URL=... python scripts/measure_kafka_linking.py --release 4.4.0
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from engine.links import link_release
from engine.projection import World, project
from linker.methods import LinkStatus
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine

_KEY = re.compile(r"\bKAFKA-\d+\b", re.IGNORECASE)


def why_feature(world: World, key: str) -> str:
    """Which part of the ADR-0018 rule made the item a feature (first that applies)."""
    f = world.features[key]
    if f.item_type == "feature":
        return "new_feature"
    if f.child_keys:
        return "umbrella"
    return "kip"


def measure(world: World, release_key: str) -> dict[str, object]:
    """Coverage numbers for one release."""
    release = world.releases[release_key]
    start, end = release.cycle_start_at, release.release_at or world.as_of
    features = world.features_ever_in(release_key)
    in_now = [f for f in features if release_key in f.release_keys]
    links = link_release(world, release_key)
    verified = [c for c in links.best.values() if c.status is LinkStatus.VERIFIED]
    suggested = [c for c in links.best.values() if c.status is LinkStatus.SUGGESTED]
    with_pr = {c.work_item_key for c in verified}

    def in_window(pr_key: str) -> bool:
        pr = world.pull_requests[pr_key]
        created = start is None or start <= pr.created_at <= end
        merged = pr.merged_at is not None and (start is None or start <= pr.merged_at <= end)
        return created or merged

    window = sorted(k for k in world.pull_requests if in_window(k))
    linked = {c.pull_request_key for c in verified} & set(window)
    suggested_only = ({c.pull_request_key for c in suggested} & set(window)) - linked
    # Context: how many window PRs name any Kafka Jira key (bugs and tasks included).
    names_key = [
        k
        for k in window
        if _KEY.search(world.pull_requests[k].title) or _KEY.search(world.pull_requests[k].body)
    ]
    return {
        "release": release_key,
        "window": [start.isoformat() if start else None, end.isoformat()],
        "work_items_in_store": len(world.features),
        "features_ever_in_release": len(features),
        "features_in_release_now": len(in_now),
        "features_by_rule": dict(Counter(why_feature(world, f.key) for f in features)),
        "features_with_verified_pr": len(with_pr & {f.key for f in features}),
        "feature_coverage": round(len(with_pr) / len(features), 3) if features else None,
        "prs_in_window": len(window),
        "prs_with_verified_feature_link": len(linked),
        "prs_with_only_suggested_link": len(suggested_only),
        "prs_naming_any_kafka_key": len(names_key),
        "verified_links_by_method": dict(Counter(c.method.value for c in verified)),
        "verified_links_via_sub_task": sum(1 for c in verified if "via_sub_task" in c.evidence),
        "suggested_links_by_method": dict(Counter(c.method.value for c in suggested)),
    }


def main() -> None:
    """Print and save the numbers."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="4.4.0")
    parser.add_argument("--out", default="docs/results")
    args = parser.parse_args()
    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session, project="KAFKA"))
    now = datetime.now(UTC)
    result = {
        "measured_at": now.isoformat(timespec="seconds"),
        "events": len(events),
        **measure(project(events, now), f"KAFKA:{args.release}"),
    }
    text = json.dumps(result, indent=2)
    print(text)
    out = Path(args.out) / f"kafka-linking-{args.release}-{now:%Y%m%d}.json"
    if out.parent.is_dir():
        out.write_text(text + "\n")


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        main()
