"""Build hidden-key eval cases for the link suggester (read-only on the DB).

    DATABASE_URL=... python scripts/build_link_cases.py

Take PRs that rules linked to exactly one feature, remove their KEP references and gate
names, and store what the suggester would see. Two kinds of case, both with a known answer:

* ``positive``: the linked feature is on the shortlist. Right answer: that feature.
* ``negative``: the linked feature is taken off the shortlist. Right answer: ``null``
  (any pick is a wrong link).

Seeded sample per release. Writes ``evals/cases/agent_link_suggester.json``.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from engine.links import candidate_index, link_release
from engine.projection import project
from linker.candidates import SHORTLIST_SIZE, shortlist, strip_link_evidence
from linker.methods import LinkStatus
from pipeline.store.events_repo import iter_events
from pipeline.store.session import make_engine

OUT = Path(__file__).resolve().parent.parent / "evals" / "cases" / "agent_link_suggester.json"
SEED = 20261122


def main() -> None:
    """Write the cases file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="append", default=None)
    parser.add_argument("--positives", type=int, default=20)
    parser.add_argument("--negatives", type=int, default=10)
    args = parser.parse_args()
    rng = random.Random(SEED)  # noqa: S311 - a reproducible sample, not security

    with Session(make_engine(instrument=False)) as session:
        events = list(iter_events(session, project="kubernetes"))
    world = project(events, max(e.occurred_at for e in events) + timedelta(days=1))

    cases = []
    for name in args.release or ["v1.37", "v1.38"]:
        key = f"kubernetes:{name}"
        feats = world.features_ever_in(key)
        numbers = [f.number for f in feats]
        gates = [g for f in feats for g in f.feature_flags]
        index = candidate_index(world, key)
        links = link_release(world, key, link_pack="kep")
        truth: dict[str, set[str]] = {}
        for (pr, item), c in links.best.items():
            if c.status is LinkStatus.VERIFIED:
                truth.setdefault(pr, set()).add(item)
        single = sorted(pr for pr, items in truth.items() if len(items) == 1)
        rng.shuffle(single)

        pos: list[dict[str, object]] = []
        neg: list[dict[str, object]] = []
        for pr_key in single:
            if len(pos) >= args.positives and len(neg) >= args.negatives:
                break
            pr = world.pull_requests[pr_key]
            (feature,) = truth[pr_key]
            title = strip_link_evidence(pr.title, numbers, gates)
            body = strip_link_evidence(pr.body, numbers, gates)
            ranked = shortlist(title, body, pr.labels, index, size=SHORTLIST_SIZE + 1)
            on_list = any(c.feature.key == feature for c in ranked[:SHORTLIST_SIZE])
            if len(pos) < args.positives and on_list:
                kind, chosen, want = "positive", ranked[:SHORTLIST_SIZE], feature
                bucket = pos
            elif len(neg) < args.negatives and len(ranked) > 1:
                kind = "negative"
                chosen = [c for c in ranked if c.feature.key != feature][:SHORTLIST_SIZE]
                want, bucket = None, neg
            else:
                continue
            bucket.append(
                {
                    "id": f"{name}-{kind}-{pr.number}",
                    "kind": kind,
                    "release": key,
                    "pull_request": {
                        "key": pr.key,
                        "title": title,
                        "body": body,
                        "labels": list(pr.labels),
                    },
                    "candidates": [{**asdict(c), "feature": asdict(c.feature)} for c in chosen],
                    "expected_feature": want,
                    "linked_feature": feature,
                }
            )
        cases += pos + neg
    OUT.write_text(json.dumps({"seed": SEED, "cases": cases}, indent=1) + "\n")
    print(f"wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
