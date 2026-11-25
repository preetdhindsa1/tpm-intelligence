"""The RAID store behind the RAID API (#180): real items, the contract's shapes.

``StoreRaid`` offers the same calls as the synthetic ``FixtureRaid`` and turns stored
``RaidItem`` rows into contract dicts. Sources link to the meeting-notes document; the
approver's login in the history is kept for audit and never returned.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from modules.raid.store import RaidItem, RaidStore

DOC_URL = "https://docs.google.com/document/d/{}"
_ENHANCEMENTS = "kubernetes/enhancements#"


def link_out(ref: str) -> dict[str, Any]:
    """An explicit key parsed from the verified quote (rule, not AI): ``explicit_key``."""
    kind = "feature" if ref.startswith(_ENHANCEMENTS) else "issue"  # issues and PRs share numbers
    return {"kind": kind, "ref": ref, "method": "explicit_key", "status": "verified"}


def item_out(item: RaidItem, titles: Mapping[str, str]) -> dict[str, Any]:
    """One stored item as the contract's ``RaidItemOut``."""
    day = datetime.fromisoformat(item.meeting_date).replace(tzinfo=UTC)
    title = titles.get(item.document_id, "Meeting notes")
    at = [h.at for h in item.history] or [day]
    return {
        "item_id": item.item_id,
        "raid_id": item.raid_id,
        "workstream": item.workstream,
        "type": item.type,
        "title": item.title,
        "quote": item.quote,
        "source": {
            "kind": "meeting",
            "title": f"{title}, {item.meeting_date}",
            "url": DOC_URL.format(item.document_id),
            "date": day,
            "synthetic": False,
        },
        "owner": item.owner,
        "status": item.status,
        "review": item.review,
        "links": [link_out(r) for r in item.links],
        "merge_suggestion": (
            {"into_item_id": item.merge_into, "reason": item.merge_reason}
            if item.merge_into is not None and item.merge_reason
            else None
        ),
        "created_at": at[0],
        "updated_at": at[-1],
    }


class StoreRaid:
    """Real RAID items for one release (``project:release``), read through ``RaidStore``."""

    synthetic = False

    def __init__(
        self,
        store: Callable[[], RaidStore],
        titles: Mapping[str, str],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store  # created on first use, so the app starts without a database
        self._titles = titles
        self._now = now

    def _all(self, release_key: str) -> list[RaidItem]:
        return self._store().items(release_key)

    def all_items(self, release_key: str) -> list[dict[str, Any]]:
        return [item_out(i, self._titles) for i in self._all(release_key)]

    def items(self, release_key: str, *, queue: bool) -> list[dict[str, Any]]:
        wanted = ("suggested",) if queue else ("confirmed", "edited")
        return [i for i in self.all_items(release_key) if i["review"] in wanted]

    def _one(self, item_id: int) -> RaidItem:
        found = self._store().get(item_id)
        if found is None:
            raise KeyError(item_id)
        return found

    def get(self, item_id: int) -> dict[str, Any]:
        return item_out(self._one(item_id), self._titles)

    def history(self, item_id: int) -> list[dict[str, Any]]:
        return [
            {"at": h.at, "actor": h.actor, "action": h.action, "changes": h.changes,
             "reason": h.reason}
            for h in self._one(item_id).history
        ]  # fmt: skip

    def decide(
        self, item_id: int, action: str, changes: dict[str, Any], reason: str | None, by: str
    ) -> dict[str, Any]:
        item = self._store().decide(item_id, action, by, self._now(), changes, reason)  # type: ignore[arg-type]
        return item_out(item, self._titles)
