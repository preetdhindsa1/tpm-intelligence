"""Every release the cloud poller is told to poll must exist in that team's calendar.

Renaming a calendar release without changing the poller's Terraform variables made every
5-minute poll crash for that team (2026-11-25). This reads the defaults in
infra/variables.tf, so the two cannot drift apart again.
"""

from __future__ import annotations

import re
from pathlib import Path

from collectors.github_poller.calendar import load_calendar
from connectors import load_team

ROOT = Path(__file__).resolve().parents[2]
VARIABLES = (ROOT / "infra" / "variables.tf").read_text()


def _default(name: str) -> str:
    block = re.search(rf'variable "{name}" \{{(.*?)\n\}}', VARIABLES, re.DOTALL)
    assert block, f"variable {name} not found in infra/variables.tf"
    value = re.search(r"default\s*=\s*(.+)", block.group(1))
    assert value, f"variable {name} has no default"
    return value.group(1).strip()


def _polled() -> dict[str, str]:
    teams = dict(re.findall(r'"([^"]+)"\s*=\s*"([^"]+)"', _default("extra_poll_teams")))
    teams["kubernetes"] = _default("poll_release").strip('"')
    return teams


def test_every_polled_release_is_in_its_teams_calendar() -> None:
    polled = _polled()
    assert polled["tpm-intelligence"] == "Phase 3"
    for team_id, release in polled.items():
        team = load_team(team_id)
        calendar = load_calendar(team.calendar_path(relative_to=ROOT))
        assert calendar.get(release).name == release, f"{team_id}: {release} missing from calendar"
