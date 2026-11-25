"""RAID tracker API (Wave 4, ADR-0030; contract: docs/api/raid-contract.md).

With a database (``DATABASE_URL``), the endpoints serve the RAID store (``api.raid_store``):
real items extracted from public meeting notes, ``"synthetic": false``. Without one (tests,
a laptop without Postgres) they serve a **synthetic** fixture, and every response says
``"synthetic": true``; decisions against the fixture change only this process's copy.

AI never confirms an item: an item stays ``suggested`` until a person confirms, edits or
rejects it here, and it gets its RAID ID (``{WORKSTREAM}-{TYPE}-{SEQ}``) on first confirm.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from api.raid_schemas import (
    TYPE_LETTER,
    RaidConfirmIn,
    RaidEditIn,
    RaidHistoryOut,
    RaidItemOut,
    RaidListOut,
    RaidRejectIn,
    RaidSummaryOut,
)

# ---- synthetic fixture ----------------------------------------------------------------------

_T0 = datetime(2026, 11, 10, 17, 0, tzinfo=UTC)
_SOURCE = {
    "kind": "meeting",
    "title": "Synthetic release-team meeting (fixture, not real notes)",
    "url": None,
    "date": _T0,
    "synthetic": True,
}


def _item(item_id: int, typ: str, title: str, quote: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "item_id": item_id,
        "raid_id": None,
        "workstream": "K8S",
        "type": typ,
        "title": title,
        "quote": quote,
        "source": dict(_SOURCE),
        "owner": None,
        "status": "open",
        "review": "suggested",
        "links": [],
        "merge_suggestion": None,
        "created_at": _T0,
        "updated_at": _T0,
    }
    base.update(kw)
    return base


def fixture_items() -> list[dict[str, Any]]:
    """Six synthetic items covering every type, review state and a merge suggestion."""
    link = {
        "kind": "feature",
        "ref": "kubernetes/enhancements#6395",
        "method": "explicit_key",
        "status": "verified",
    }
    merge = {"into_item_id": 4, "reason": "Same CI job and the same week as item 4."}
    # fmt: off
    return [
        _item(1, "risk", "Main PR for enhancement #6395 may miss Code Freeze",
              "Synthetic: the main PR for #6395 still needs an approver from SIG Storage.",
              raid_id="K8S-R-001", review="confirmed", owner="SIG Storage", links=[link]),
        _item(2, "action", "Release lead to send the Code Freeze reminder",
              "Synthetic: send the code freeze reminder to all SIG leads by Friday.",
              raid_id="K8S-A-001", review="edited", owner="Release lead", status="closed"),
        _item(3, "decision", "Exceptions are reviewed in the Tuesday meeting",
              "Synthetic: we agreed exception requests are reviewed every Tuesday.",
              raid_id="K8S-D-001", review="confirmed", owner="Release team"),
        _item(4, "risk", "CI flakes on the node e2e job",
              "Synthetic: node e2e has been flaky all week."),
        _item(5, "risk", "Node e2e job is unstable",
              "Synthetic: the node e2e job keeps failing for unrelated PRs.",
              merge_suggestion=merge),
        _item(6, "question", "Does the docs freeze move with the release date?",
              "Synthetic: does docs freeze move if the release slips?",
              review="rejected", status="superseded"),
    ]
    # fmt: on


def _history(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "at": item["created_at"],
            "actor": "extractor",
            "action": "suggested",
            "changes": {"type": item["type"], "title": item["title"]},
            "reason": None,
        }
    ]
    if item["review"] != "suggested":
        rows.append(
            {
                "at": item["updated_at"],
                "actor": "approver",
                "action": item["review"],
                "changes": {"raid_id": item["raid_id"]} if item["raid_id"] else {},
                "reason": "Synthetic reason" if item["review"] == "rejected" else None,
            }
        )
    return rows


class FixtureRaid:
    """In-memory synthetic RAID data for one process, used when no database is configured.

    It has one scope (kubernetes v1.38): the ``release_key`` arguments are ignored.
    """

    synthetic = True

    def __init__(self, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._items = {i["item_id"]: i for i in fixture_items()}
        self._history = {k: _history(v) for k, v in self._items.items()}

    def all_items(self, release_key: str = "") -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(i) for i in self._items.values()]

    def items(self, release_key: str = "", *, queue: bool) -> list[dict[str, Any]]:
        rows = self.all_items()
        if queue:
            return [i for i in rows if i["review"] == "suggested"]
        return [i for i in rows if i["review"] in ("confirmed", "edited")]

    def get(self, item_id: int) -> dict[str, Any]:
        with self._lock:
            if item_id not in self._items:
                raise KeyError(item_id)
            return copy.deepcopy(self._items[item_id])

    def history(self, item_id: int) -> list[dict[str, Any]]:
        self.get(item_id)
        with self._lock:
            return copy.deepcopy(self._history[item_id])

    def decide(
        self, item_id: int, action: str, changes: dict[str, Any], reason: str | None, by: str = ""
    ) -> dict[str, Any]:
        """Confirm, edit or reject; a RAID ID is given on the first confirm or edit."""
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                raise KeyError(item_id)
            if item["review"] == "rejected":
                raise ValueError("a rejected item cannot be decided again")
            now = self._now()
            item.update({k: v for k, v in changes.items() if v is not None})
            item["review"] = action
            if action != "rejected" and item["raid_id"] is None:
                item["raid_id"] = self._next_id(item["workstream"], item["type"])
                changes = {**changes, "raid_id": item["raid_id"]}
            item["updated_at"] = now
            self._history[item_id].append(
                {
                    "at": now,
                    "actor": "approver",
                    "action": action,
                    "changes": {k: v for k, v in changes.items() if v is not None},
                    "reason": reason,
                }
            )
            return copy.deepcopy(item)

    def _next_id(self, workstream: str, typ: str) -> str:
        prefix = f"{workstream}-{TYPE_LETTER[typ]}-"
        used = [
            int(i["raid_id"][len(prefix) :])
            for i in self._items.values()
            if i["raid_id"] and i["raid_id"].startswith(prefix)
        ]
        return f"{prefix}{max(used, default=0) + 1:03d}"


def summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts by type: suggested and rejected by review, the rest by lifecycle status."""
    rows = []
    for typ in TYPE_LETTER:
        mine = [i for i in items if i["type"] == typ]
        live = [i for i in mine if i["review"] in ("confirmed", "edited")]
        rows.append(
            {
                "type": typ,
                "suggested": sum(1 for i in mine if i["review"] == "suggested"),
                "rejected": sum(1 for i in mine if i["review"] == "rejected"),
                **{
                    s: sum(1 for i in live if i["status"] == s)
                    for s in ("open", "in_progress", "closed", "superseded")
                },
            }
        )
    no_owner = sum(
        1
        for i in items
        if i["type"] == "risk"
        and i["review"] in ("confirmed", "edited")
        and i["status"] in ("open", "in_progress")
        and not i["owner"]
    )
    waiting = sum(1 for i in items if i["review"] == "suggested")
    return {"by_type": rows, "risks_without_owner": no_owner, "waiting_for_review": waiting}


# ---- routes ---------------------------------------------------------------------------------


def raid_router(
    approver: Callable[[Request], Awaitable[Any]],
    data: Any = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> APIRouter:
    """RAID endpoints. ``approver`` is the app's sign-in dependency (ADR-0016).

    ``data`` is a ``FixtureRaid`` (synthetic) or an ``api.raid_store.StoreRaid`` (real).
    """
    router = APIRouter(tags=["raid"])
    raid = data or FixtureRaid(now)
    fake = bool(raid.synthetic)

    def scope(project: str, release: str) -> dict[str, Any]:
        return {"project": project, "release": release, "as_of": now(), "synthetic": fake}

    def found(item_id: int) -> dict[str, Any]:
        try:
            return raid.get(item_id)
        except KeyError as exc:
            raise HTTPException(404, f"unknown RAID item {item_id}") from exc

    def listing(project: str, release: str, queue: bool) -> RaidListOut:
        items = raid.items(f"{project}:{release}", queue=queue)
        return RaidListOut.model_validate({**scope(project, release), "items": items})

    @router.get("/raid", response_model=RaidListOut)
    async def raid_list(project: str = "kubernetes", release: str = "v1.38") -> RaidListOut:
        """Confirmed and edited items (the tracker). Suggested items are in /raid/queue."""
        return listing(project, release, queue=False)

    @router.get("/raid/queue", response_model=RaidListOut)
    async def raid_queue(project: str = "kubernetes", release: str = "v1.38") -> RaidListOut:
        """Items the extractor suggested, waiting for a person."""
        return listing(project, release, queue=True)

    @router.get("/raid/summary", response_model=RaidSummaryOut)
    async def raid_summary(project: str = "kubernetes", release: str = "v1.38") -> RaidSummaryOut:
        """Counts by type and state, risks without an owner, items waiting for review."""
        counts = summary(raid.all_items(f"{project}:{release}"))
        return RaidSummaryOut.model_validate({**scope(project, release), **counts})

    @router.get("/raid/{item_id}/history", response_model=RaidHistoryOut)
    async def raid_history(item_id: int) -> RaidHistoryOut:
        """Every change to the item, oldest first (append-only)."""
        item = found(item_id)
        return RaidHistoryOut.model_validate(
            {
                "item_id": item_id,
                "raid_id": item["raid_id"],
                "synthetic": fake,
                "history": raid.history(item_id),
            }
        )

    def decide(
        item_id: int, action: str, changes: dict[str, Any], reason: str | None, who: Any
    ) -> RaidItemOut:
        found(item_id)
        by = str(getattr(who, "login", None) or "")  # audit only, never returned
        try:
            return RaidItemOut.model_validate(raid.decide(item_id, action, changes, reason, by))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/raid/{item_id}/confirm", response_model=RaidItemOut)
    async def raid_confirm(
        item_id: int, body: RaidConfirmIn, who: Any = Depends(approver)
    ) -> RaidItemOut:
        """A person confirms the item as suggested. It gets its RAID ID now."""
        return decide(item_id, "confirmed", {}, body.note, who)

    @router.post("/raid/{item_id}/edit", response_model=RaidItemOut)
    async def raid_edit(
        item_id: int, body: RaidEditIn, who: Any = Depends(approver)
    ) -> RaidItemOut:
        """A person corrects and confirms the item. The quote stays the source's words."""
        changes = body.model_dump(exclude={"note"}, exclude_none=True)
        return decide(item_id, "edited", changes, body.note, who)

    @router.post("/raid/{item_id}/reject", response_model=RaidItemOut)
    async def raid_reject(
        item_id: int, body: RaidRejectIn, who: Any = Depends(approver)
    ) -> RaidItemOut:
        """A person rejects the item, with a reason. It never gets a RAID ID."""
        return decide(item_id, "rejected", {}, body.reason, who)

    return router
