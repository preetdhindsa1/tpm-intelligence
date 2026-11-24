"""Load team connector YAML from ``connectors/teams/``."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import yaml

from connectors.schema import TeamConfig


class _Key(Protocol):
    @property
    def external_key(self) -> str: ...


class _Subject(Protocol):
    @property
    def subject(self) -> _Key: ...


_TEAMS = Path(__file__).resolve().parent / "teams"


def teams_dir() -> Path:
    """Directory that holds ``<team-id>.yaml`` files."""
    return _TEAMS


def load_team(team_id: str, *, directory: Path | None = None) -> TeamConfig:
    """Load one team by id (filename stem)."""
    root = directory or teams_dir()
    path = root / f"{team_id}.yaml"
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in root.glob("*.yaml") if not p.name.startswith("_")))
        raise FileNotFoundError(f"team {team_id!r} not found in {root} (known: {known})")
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    config = TeamConfig.model_validate(raw)
    if config.id != team_id:
        raise ValueError(f"{path}: id {config.id!r} does not match filename stem {team_id!r}")
    return config


def _is_team_file(path: Path) -> bool:
    """Team defs are ``<id>.yaml``; skip templates and ``*-calendar.yaml`` sidecars."""
    name = path.name
    return (
        name.endswith(".yaml") and not name.startswith("_") and not name.endswith("-calendar.yaml")
    )


@lru_cache(maxsize=1)
def load_teams() -> dict[str, TeamConfig]:
    """All non-template teams, keyed by id."""
    out: dict[str, TeamConfig] = {}
    for path in sorted(teams_dir().glob("*.yaml")):
        if not _is_team_file(path):
            continue
        config = load_team(path.stem)
        out[config.id] = config
    return out


def display_name_for_project(project: str) -> str:
    """Human label for a release project key, falling back to the raw project id."""
    for team in load_teams().values():
        if team.project == project:
            return team.display_name
    return project


def link_pack_for_project(project: str) -> str:
    """Linker pack name for a release project (default ``kep``)."""
    for team in load_teams().values():
        if team.project == project:
            return team.link_pack
    return "kep"


def team_for_project(project: str) -> TeamConfig | None:
    """The team whose release keys use ``project`` (None if no team file says so)."""
    return next((t for t in load_teams().values() if t.project == project), None)


def projects_owning(subject_key: str) -> set[str]:
    """Projects whose world an event subject belongs to (empty if no team owns it)."""
    return {t.project for t in load_teams().values() if t.owns(subject_key)}


def scope_events[E: _Subject](events: Iterable[E], project: str) -> list[E]:
    """Only the events of one project's world (ADR-0018).

    Each project gets its own world, so Kafka PRs never count as Kubernetes reviewer load
    and one project's releases never calibrate another. Unknown projects keep every event.
    """
    team = team_for_project(project)
    if team is None:
        return list(events)
    return [e for e in events if team.owns(e.subject.external_key)]


def clear_team_cache() -> None:
    """Test helper."""
    load_teams.cache_clear()
