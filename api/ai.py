"""AI features for the API: fact sheets from release views, and risk notes (M3a)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from agents.gateway import Gateway
from agents.notes import NoteStore
from agents.risk_analyst import NoteResult, risk_note
from agents.updates import ExecUpdate, UpdateStore
from api.service import ReleaseView
from engine.assess import FeatureAssessment
from verify.build import OddsFacts, build_fact_sheet
from verify.claims import Claim
from verify.facts import FactSheet


def fact_sheet_for(view: ReleaseView) -> FactSheet:
    """Every citable fact for a computed release view (odds carry their validation status)."""
    odds = {
        key: OddsFacts(
            probability=fc.probability,
            low=fc.low,
            high=fc.high,
            base_rate=view.recalibration.base_rate,
            validated=view.validation.validated,
        )
        for key, fc in view.forecasts.items()
        if fc.status == "forecast"
    }
    return build_fact_sheet(view.assessment, odds)


@dataclass
class AIServices:
    """Gateway and note store, created on first use so the API starts without an AI key."""

    gateway: Gateway | None = None
    notes: NoteStore | None = None
    updates: UpdateStore | None = None
    _sheets: dict[tuple[str, int], FactSheet] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _ensure(self) -> tuple[Gateway, NoteStore, UpdateStore]:
        with self._lock:
            if self.gateway is None or self.notes is None or self.updates is None:
                from sqlalchemy.orm import sessionmaker

                from agents.ledger import PostgresLedger
                from agents.notes import PostgresNoteStore
                from agents.settings import AISettings
                from agents.updates import PostgresUpdateStore
                from pipeline.store.session import make_engine

                factory: Any = sessionmaker(make_engine())
                self.gateway = self.gateway or Gateway(AISettings(), PostgresLedger(factory))
                self.notes = self.notes or PostgresNoteStore(factory)
                self.updates = self.updates or PostgresUpdateStore(factory)
            return self.gateway, self.notes, self.updates

    def sheet(self, view: ReleaseView) -> FactSheet:
        """Fact sheet per (release, view version), cached."""
        key = (view.assessment.release.key, view.version)
        with self._lock:
            if key not in self._sheets:
                self._sheets = {key: fact_sheet_for(view)}  # keep only the newest
            return self._sheets[key]

    def risk_note(
        self, view: ReleaseView, feature: FeatureAssessment, *, generate: bool = True
    ) -> NoteResult:
        """Verified risk note for a feature; calls Claude only if ``generate`` is set."""
        gateway, notes, _ = self._ensure()
        return risk_note(
            gateway,
            notes,
            view.assessment.release.key,
            feature,
            self.sheet(view),
            generate=generate,
        )

    # ---------------------------------------------------------------- executive updates

    def draft(self, view: ReleaseView) -> ExecUpdate:
        """Draft a new update (essential AI call)."""
        from agents.vp_summary import draft_update

        gateway, _, updates = self._ensure()
        return draft_update(
            gateway,
            updates,
            view.assessment.release.key,
            list(view.assessment.features),
            self.sheet(view),
            odds_validated=view.validation.validated,
        )

    def list_updates(self, view: ReleaseView) -> list[tuple[ExecUpdate, bool]]:
        """Updates for a release, newest first, each with whether it is stale."""
        _, _, updates = self._ensure()
        return [(u, self.stale(view, u)) for u in updates.list(view.assessment.release.key)]

    def get_update(self, update_id: int) -> ExecUpdate | None:
        """One update."""
        _, _, updates = self._ensure()
        return updates.get(update_id)

    def stale(self, view: ReleaseView, update: ExecUpdate) -> bool:
        """Facts changed meaningfully since the draft (decided drafts are never stale)."""
        from agents.updates import UpdateStatus
        from agents.vp_summary import is_stale

        if update.status is not UpdateStatus.DRAFT:
            return False
        return is_stale(update, list(view.assessment.features), self.sheet(view))[0]

    def edit(self, update_id: int, sections: dict[str, list[Claim]]) -> ExecUpdate:
        """Save TPM edits and re-check them."""
        from agents.vp_summary import edit_update

        _, _, updates = self._ensure()
        return edit_update(updates, update_id, sections)

    def decide(
        self, view: ReleaseView, update_id: int, *, approve: bool, approver: str, **kwargs: Any
    ) -> ExecUpdate:
        """Approve or reject, recording the signed-in approver (ADR-0016)."""
        from agents.vp_summary import decide

        _, _, updates = self._ensure()
        update = updates.get(update_id)
        if update is None:
            raise KeyError(update_id)
        return decide(
            updates,
            update_id,
            approve=approve,
            approver=approver,
            stale=self.stale(view, update),
            **kwargs,
        )
