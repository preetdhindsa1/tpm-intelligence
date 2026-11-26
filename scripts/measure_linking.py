"""Measure linking coverage on real backfilled data (read-only).

Reads the latest snapshots from the ``events`` table, runs the deterministic linker, and
prints coverage numbers for the README. Usage::

    DATABASE_URL=... python scripts/measure_linking.py --release v1.38
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from linker.methods import LinkStatus
from linker.rules import LinkIndex, PullRequestInfo, WorkItemInfo, best_links, link_pull_request
from pipeline.store.session import make_engine

LATEST = """
SELECT DISTINCT ON (subject_key) subject_key, payload
FROM events WHERE event_type = :t
ORDER BY subject_key, occurred_at DESC, id DESC
"""
MEMBERSHIP = """
SELECT DISTINCT ON (subject_key) subject_key, payload->>'action' AS action
FROM events
WHERE event_type = 'work_item.release_changed' AND payload->>'release_key' = :rk
ORDER BY subject_key, occurred_at DESC, id DESC
"""


def main() -> None:
    """Print coverage as JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="v1.38")
    args = parser.parse_args()
    release_key = f"kubernetes:{args.release}"

    engine = make_engine(instrument=False)
    with engine.connect() as conn:
        items: dict[str, Any] = dict(conn.execute(text(LATEST), {"t": "work_item.observed"}).all())
        specs: dict[str, Any] = dict(
            conn.execute(text(LATEST), {"t": "work_item.spec_observed"}).all()
        )
        prs: dict[str, Any] = dict(conn.execute(text(LATEST), {"t": "pull_request.observed"}).all())
        membership = dict(conn.execute(text(MEMBERSHIP), {"rk": release_key}).all())

    in_release = {k for k, action in membership.items() if action == "added"}
    tracked = {k for k in in_release if "tracked/yes" in items.get(k, {}).get("labels", [])}
    infos = [
        WorkItemInfo(
            key=k,
            number=int(k.rsplit("#", 1)[1]),
            description=items[k].get("description", ""),
            feature_flags=tuple(specs.get(k, {}).get("feature_flags", [])),
            labels=tuple(items[k].get("labels", [])),
        )
        for k in in_release
        if k in items
    ]
    index = LinkIndex.build(infos)

    best = {}
    for key, p in prs.items():
        info = PullRequestInfo(
            key=key,
            repo=p["repo"],
            number=p["number"],
            title=p["title"],
            body=p.get("body", ""),
            labels=tuple(p.get("labels", [])),
        )
        best.update(best_links(link_pull_request(info, index)))

    verified = [c for c in best.values() if c.status is LinkStatus.VERIFIED]
    suggested = [c for c in best.values() if c.status is LinkStatus.SUGGESTED]
    features_with_verified = {c.work_item_key for c in verified}
    prs_verified = {c.pull_request_key for c in verified}
    prs_suggested_only = {c.pull_request_key for c in suggested} - prs_verified

    result = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "release": args.release,
        "features_in_release_now": len(in_release),
        "features_tracked_now": len(tracked),
        "tracked_features_with_verified_pr": len(features_with_verified & tracked),
        "tracked_feature_coverage": round(len(features_with_verified & tracked) / len(tracked), 3)
        if tracked
        else None,
        "prs_in_window": len(prs),
        "prs_with_verified_link": len(prs_verified),
        "prs_with_only_suggested_link": len(prs_suggested_only),
        "prs_unlinked": len(prs) - len(prs_verified) - len(prs_suggested_only),
        "verified_links_by_method": dict(Counter(c.method.value for c in verified)),
        "suggested_links_by_method": dict(Counter(c.method.value for c in suggested)),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        main()
