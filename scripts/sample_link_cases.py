"""Draw a stratified sample of PR -> feature links for hand labelling (read-only on the DB).

    DATABASE_URL=... python scripts/sample_link_cases.py --release v1.38 [--seed 1338]

Writes ``evals/cases/linking.csv``: up to ``--per-method`` verified links per method, up to
``--suggested`` suggested links, and ``--unlinked`` PRs with no link. Fill the ``label``
column: ``yes`` / ``no`` / ``unsure``. For unlinked rows, ``yes`` means "correctly
unlinked"; if the PR belongs to a feature, write ``no`` and put the feature number in
``notes``. The seed makes the sample reproducible.
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import text

from linker.methods import LinkStatus
from linker.rules import LinkIndex, PullRequestInfo, WorkItemInfo, best_links, link_pull_request
from pipeline.store.session import make_engine

OUT = Path(__file__).resolve().parent.parent / "evals" / "cases" / "linking.csv"
LATEST = """
SELECT DISTINCT ON (subject_key) subject_key, payload
FROM events WHERE event_type = :t
ORDER BY subject_key, occurred_at DESC, id DESC
"""
EVER_IN = """
SELECT DISTINCT subject_key FROM events
WHERE event_type = 'work_item.release_changed' AND payload->>'release_key' = :rk
"""
COLUMNS = [
    "case_id", "status", "method", "pr", "pr_title", "pr_url",
    "feature", "feature_title", "label", "notes",
]  # fmt: skip


def main() -> None:
    """Sample and write the CSV."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="v1.38")
    parser.add_argument("--seed", type=int, default=1338)
    parser.add_argument("--per-method", type=int, default=10)
    parser.add_argument("--suggested", type=int, default=15)
    parser.add_argument("--unlinked", type=int, default=10)
    args = parser.parse_args()
    release_key = f"kubernetes:{args.release}"

    with make_engine(instrument=False).connect() as conn:
        items: dict[str, Any] = dict(conn.execute(text(LATEST), {"t": "work_item.observed"}).all())
        specs: dict[str, Any] = dict(
            conn.execute(text(LATEST), {"t": "work_item.spec_observed"}).all()
        )
        prs: dict[str, Any] = dict(conn.execute(text(LATEST), {"t": "pull_request.observed"}).all())
        ever_in = {row[0] for row in conn.execute(text(EVER_IN), {"rk": release_key}).all()}

    infos = [
        WorkItemInfo(
            key=k,
            number=int(k.rsplit("#", 1)[1]),
            description=items[k].get("description", ""),
            feature_flags=tuple(specs.get(k, {}).get("feature_flags", [])),
            labels=tuple(items[k].get("labels", [])),
        )
        for k in sorted(ever_in)
        if k in items
    ]
    index = LinkIndex.build(infos)

    groups: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    linked: set[str] = set()
    for key in sorted(prs):
        p = prs[key]
        info = PullRequestInfo(
            key=key,
            repo=p["repo"],
            number=p["number"],
            title=p["title"],
            body=p.get("body", ""),
            labels=tuple(p.get("labels", [])),
        )
        for c in best_links(link_pull_request(info, index)).values():
            if c.status is LinkStatus.REJECTED:
                continue
            linked.add(key)
            groups[(c.status.value, c.method.value)].append((key, c.work_item_key))
    unlinked = [(k, "") for k in sorted(prs) if k not in linked]

    rng = random.Random(args.seed)  # noqa: S311 - reproducible sampling, not security
    rows: list[dict[str, str]] = []

    def take(status: str, method: str, pairs: list[tuple[str, str]], n: int) -> None:
        for pr_key, feature in rng.sample(pairs, min(n, len(pairs))):
            p = prs[pr_key]
            rows.append(
                {
                    "case_id": f"L{len(rows) + 1:03d}",
                    "status": status,
                    "method": method,
                    "pr": pr_key,
                    "pr_title": p["title"],
                    "pr_url": p.get("url", ""),
                    "feature": feature,
                    "feature_title": items.get(feature, {}).get("title", "") if feature else "",
                    "label": "",
                    "notes": "",
                }
            )

    for (status, method), pairs in sorted(groups.items()):
        n = args.per_method if status == LinkStatus.VERIFIED.value else args.suggested
        take(status, method, pairs, n)
    take("unlinked", "none", unlinked, args.unlinked)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        main()
