"""Confirmed RAID items as citable facts (#180). Pure, no I/O.

Only items a person confirmed or edited, and still open or in progress, become facts:
suggested items are AI output and never facts (CLAUDE.md section 2.2). Keys use the RAID
ID, so a claim cites an item as ``raid:K8S-R-001::title``::

    raid:K8S-R-001::type      label  risk | action | issue | decision | question
    raid:K8S-R-001::title     label  the confirmed title
    raid:K8S-R-001::status    label  open | in_progress
    raid:K8S-R-001::owner     label  a role or team (absent when nobody owns it)
    raid:K8S-R-001::feature   label  a linked feature key, when the quote names one
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from modules.raid.store import RaidItem
from verify.facts import Fact, FactKind, fact_key

LIVE = ("open", "in_progress")
_FEATURE = "kubernetes/enhancements#"


def raid_facts(items: Iterable[RaidItem]) -> Iterator[Fact]:
    """Facts for confirmed, open RAID items, ordered by RAID ID."""
    live = [
        i for i in items
        if i.raid_id and i.review in ("confirmed", "edited") and i.status in LIVE
    ]  # fmt: skip
    for item in sorted(live, key=lambda i: str(i.raid_id)):

        def fact(field: str, value: str, it: RaidItem = item) -> Fact:
            return Fact(fact_key("raid", field, it.raid_id), FactKind.LABEL, value)

        yield fact("type", item.type)
        yield fact("title", item.title)
        yield fact("status", item.status)
        if item.owner:
            yield fact("owner", item.owner)
        feature = next((ref for ref in item.links if ref.startswith(_FEATURE)), None)
        if feature:
            yield fact("feature", feature)
