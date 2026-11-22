"""Shortlist recall on rule-linked PRs with their keys hidden (read-only on the DB).

    DATABASE_URL=... python scripts/measure_shortlist.py --release v1.38 --release v1.37

For every PR with a verified link to a feature in the release, remove the KEP references
and gate names from its text, build the shortlist, and report how often the linked feature
is on it (and at which rank). Prints JSON.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from engine.links import candidate_index, link_release
from engine.projection import World, project
from linker.candidates import SHORTLIST_SIZE, shortlist, strip_link_evidence
from linker.methods import LinkStatus
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine


def measure(world: World, release_key: str, size: int) -> dict[str, object]:
    """Recall at ``size`` and rank distribution."""
    feats = world.features_ever_in(release_key)
    numbers = [f.number for f in feats]
    gates = [g for f in feats for g in f.feature_flags]
    index = candidate_index(world, release_key)
    links = link_release(world, release_key, link_pack="kep")
    truth: dict[str, set[str]] = {}
    for (pr, item), c in links.best.items():
        if c.status is LinkStatus.VERIFIED:
            truth.setdefault(pr, set()).add(item)
    ranks: Counter[str] = Counter()
    for pr_key, items in truth.items():
        pr = world.pull_requests[pr_key]
        title = strip_link_evidence(pr.title, numbers, gates)
        body = strip_link_evidence(pr.body, numbers, gates)
        found = [
            c.rank
            for c in shortlist(title, body, pr.labels, index, size=size)
            if c.feature.key in items
        ]
        ranks[str(min(found)) if found else "miss"] += 1
    n = sum(ranks.values())
    return {
        "release": release_key,
        "features": len(feats),
        "linked_prs": n,
        f"recall_at_{size}": round((n - ranks["miss"]) / n, 3) if n else None,
        "recall_at_1": round(ranks["1"] / n, 3) if n else None,
        "rank_counts": dict(sorted(ranks.items())),
    }


def main() -> None:
    """Print recall per release."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="append", default=None)
    parser.add_argument("--size", type=int, default=SHORTLIST_SIZE)
    args = parser.parse_args()
    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session))
    world = project(events, max(e.occurred_at for e in events) + timedelta(days=1))
    out = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "shortlist_size": args.size,
        "releases": [
            measure(world, f"kubernetes:{r}", args.size) for r in args.release or ["v1.37", "v1.38"]
        ],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
