"""AI features for the API: fact sheets from release views, and risk notes (M3a)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from agents.gateway import Gateway
from agents.notes import NoteStore
from agents.risk_analyst import NoteResult, risk_note
from api.service import ReleaseView
from engine.assess import FeatureAssessment
from verify.build import OddsFacts, build_fact_sheet
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
    _sheets: dict[tuple[str, int], FactSheet] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _ensure(self) -> tuple[Gateway, NoteStore]:
        with self._lock:
            if self.gateway is None or self.notes is None:
                from sqlalchemy.orm import sessionmaker

                from agents.ledger import PostgresLedger
                from agents.notes import PostgresNoteStore
                from agents.settings import AISettings
                from pipeline.store.session import make_engine

                factory: Any = sessionmaker(make_engine())
                self.gateway = self.gateway or Gateway(AISettings(), PostgresLedger(factory))
                self.notes = self.notes or PostgresNoteStore(factory)
            return self.gateway, self.notes

    def sheet(self, view: ReleaseView) -> FactSheet:
        """Fact sheet per (release, view version), cached."""
        key = (view.assessment.release.key, view.version)
        with self._lock:
            if key not in self._sheets:
                self._sheets = {key: fact_sheet_for(view)}  # keep only the newest
            return self._sheets[key]

    def risk_note(self, view: ReleaseView, feature: FeatureAssessment) -> NoteResult:
        """Verified risk note for a feature (may call Claude)."""
        gateway, notes = self._ensure()
        return risk_note(gateway, notes, view.assessment.release.key, feature, self.sheet(view))
