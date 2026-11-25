"""RAID store on Postgres (migration 0010). Same rules as ``MemoryRaidStore``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from modules.raid.store import HistoryRow, RaidItem, Review, merge_reason, next_raid_id
from pipeline.store.models import RaidHistoryRecord as H
from pipeline.store.models import RaidItemRecord as R


class PostgresRaidStore:
    """``raid_items`` and ``raid_history``. History rows are only ever inserted."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def _item(rec: R, rows: list[H]) -> RaidItem:
        history = tuple(
            HistoryRow(h.at, h.actor, h.action, h.changes, h.reason, h.by_login)  # type: ignore[arg-type]
            for h in rows
        )
        return RaidItem(
            rec.id, rec.key, rec.release_key, rec.workstream, rec.type,  # type: ignore[arg-type]
            rec.title, rec.quote, rec.document_id, rec.meeting_date, rec.owner,
            rec.status, rec.review, rec.raid_id, tuple(rec.links),  # type: ignore[arg-type]
            rec.merge_into, rec.merge_reason, history,
        )  # fmt: skip

    def _load(self, s: Session, rec: R) -> RaidItem:
        rows = list(s.scalars(select(H).where(H.item_id == rec.id).order_by(H.id)))
        return self._item(rec, rows)

    def suggest(self, item: RaidItem, at: datetime) -> RaidItem | None:
        """Insert a suggestion; None if its key exists (a rejected one included)."""
        with self._sessions() as s, s.begin():
            live = select(R).where(R.release_key == item.release_key, R.review != "rejected")
            others = [self._item(r, []) for r in s.scalars(live)]
            merge = next(((o.item_id, why) for o in others if (why := merge_reason(item, o))),
                         (None, None))  # fmt: skip
            new_id = s.execute(
                insert(R).values(
                    key=item.key, release_key=item.release_key, workstream=item.workstream,
                    type=item.type, title=item.title, quote=item.quote,
                    document_id=item.document_id, meeting_date=item.meeting_date,
                    owner=item.owner, links=list(item.links), merge_into=merge[0],
                    merge_reason=merge[1], created_at=at, updated_at=at,
                ).on_conflict_do_nothing(index_elements=["key"]).returning(R.id)
            ).scalar_one_or_none()  # fmt: skip
            if new_id is None:
                return None
            s.add(H(item_id=new_id, at=at, actor="extractor", action="suggested",
                    changes={"type": item.type}))  # fmt: skip
            s.flush()
            return self._load(s, s.get_one(R, new_id))

    def decide(
        self,
        item_id: int,
        action: Review,
        by: str,
        at: datetime,
        changes: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> RaidItem:
        """A person's decision, with the same refusals as the in-memory store."""
        if action == "suggested":
            raise ValueError("only the extractor suggests")
        if action == "rejected" and not (reason and reason.strip()):
            raise ValueError("a rejection needs a reason")
        changes = {k: v for k, v in (changes or {}).items() if v is not None}
        if "quote" in changes:
            raise ValueError("the quote is the source's words and cannot be edited")
        with self._sessions() as s, s.begin():
            rec = s.get(R, item_id, with_for_update=True)
            if rec is None:
                raise KeyError(item_id)
            if rec.review == "rejected":
                raise ValueError("a rejected item cannot be decided again")
            rid = rec.raid_id
            if action != "rejected" and rid is None:
                # One ID at a time per workstream and type, so two confirms cannot collide.
                # The ID is chosen before any column changes: the row must never reach the
                # database as confirmed without one (ck_raid_items_id_on_confirm).
                prefix = f"{rec.workstream}-{rec.type}"
                s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:p))"), {"p": prefix})
                used = set(s.scalars(select(R.raid_id).where(R.raid_id.is_not(None))))
                rid = next_raid_id({u for u in used if u}, rec.workstream, rec.type)
                changes = {**changes, "raid_id": rid}
            for k, v in changes.items():
                setattr(rec, k, v)
            rec.review, rec.updated_at = action, at
            s.add(H(item_id=item_id, at=at, actor="approver", action=action, changes=changes,
                    reason=reason, by_login=by))  # fmt: skip
            s.flush()
            return self._load(s, rec)

    def items(self, release_key: str) -> list[RaidItem]:
        with self._sessions() as s:
            recs = list(s.scalars(select(R).where(R.release_key == release_key).order_by(R.id)))
            return [self._load(s, r) for r in recs]

    def get(self, item_id: int) -> RaidItem | None:
        with self._sessions() as s:
            rec = s.get(R, item_id)
            return None if rec is None else self._load(s, rec)

    def count(self) -> int:
        with self._sessions() as s:
            return int(s.scalar(select(func.count()).select_from(R)) or 0)
