"""Load the checked-in release calendar."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict

DEFAULT_PATH = Path(__file__).with_name("release_calendar.yaml")


class ReleaseDates(BaseModel):
    """Key dates for one release."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    cycle_start: AwareDatetime
    enhancements_freeze: AwareDatetime
    code_freeze: AwareDatetime
    release: AwareDatetime
    source_url: str


class Calendar(BaseModel):
    """All releases of one project."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project: str
    releases: tuple[ReleaseDates, ...]

    def get(self, name: str) -> ReleaseDates:
        """Dates for release ``name`` (e.g. ``v1.38``)."""
        for release in self.releases:
            if release.name == name:
                return release
        known = ", ".join(r.name for r in self.releases)
        raise KeyError(f"release {name!r} not in calendar (known: {known})")


def load_calendar(path: Path = DEFAULT_PATH) -> Calendar:
    """Parse and validate the calendar file."""
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    calendar = Calendar.model_validate(raw)
    for r in calendar.releases:
        ordered: list[datetime] = [r.cycle_start, r.enhancements_freeze, r.code_freeze, r.release]
        if ordered != sorted(ordered):
            raise ValueError(f"{r.name}: dates out of order")
    return calendar
