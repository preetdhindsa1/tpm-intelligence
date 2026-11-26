"""Load team connector YAML from ``connectors/teams/``."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import yaml

from connectors.schema import TeamConfig

if TYPE_CHECKING:
    from collectors.github_poller.calendar import ReleaseDates


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


_DB_TTL_S = 30.0  # private tenants' configs are re-read at most this often
_db_cache: dict[str, tuple[float, dict[str, TeamConfig]]] = {}
_db_lock = threading.Lock()
# Where private tenants' configs come from: Postgres by default, swapped in tests.
_db_source: Callable[[str], dict[str, TeamConfig]] | None = None


def load_teams(tenant: str | None = None) -> dict[str, TeamConfig]:
    """The teams of ``tenant`` (default: the current tenant), keyed by id (ADR-0035).

    The public demo's teams are the YAML files in ``connectors/teams/``. Any other tenant's
    come from its ``team_configs`` rows. With no tenant at all this refuses, rather than
    hand one tenant's teams to code running for another.
    """
    from pipeline.store.tenancy import DEMO, current_tenant

    t = tenant or current_tenant.get()
    if t is None:
        raise RuntimeError("no tenant: team configs are per tenant (ADR-0035)")
    if t == DEMO:
        return _yaml_teams()
    now = time.monotonic()
    with _db_lock:
        hit = _db_cache.get(t)
        if hit is not None and now - hit[0] < _DB_TTL_S:
            return hit[1]
    teams = (_db_source or _postgres_teams)(t)
    with _db_lock:
        _db_cache[t] = (now, teams)
    return teams


def set_team_source(source: Callable[[str], dict[str, TeamConfig]] | None) -> None:
    """Tests: read private tenants' teams from ``source`` instead of Postgres."""
    global _db_source
    _db_source = source
    clear_team_cache()


@lru_cache(maxsize=1)
def _engine() -> Any:
    from pipeline.store.session import make_engine

    return make_engine()


def _postgres_teams(tenant: str) -> dict[str, TeamConfig]:
    from sqlalchemy.orm import sessionmaker

    from connectors.store import PostgresTeamConfigStore
    from pipeline.env import configured
    from pipeline.store.tenancy import tenant_sessions

    if configured("DATABASE_URL") is None:
        return {}
    store = PostgresTeamConfigStore(tenant_sessions(sessionmaker(_engine()), tenant))
    return {row.config.id: row.config for row in store.list()}


@lru_cache(maxsize=1)
def _yaml_teams() -> dict[str, TeamConfig]:
    """All non-template team files, keyed by id: the public demo's teams."""
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


def release_plan(team: TeamConfig) -> dict[str, ReleaseDates]:
    """Hand-entered release dates by name, from the team's calendar file ({} if none).

    For a Jira team the freeze dates come from here (#8); Jira gives the rest.
    """
    from collectors.github_poller.calendar import load_calendar

    path = team.calendar_path(relative_to=teams_dir().parent.parent)
    if not path.is_file():
        return {}
    calendar = load_calendar(path)
    if calendar.project != team.project:
        raise ValueError(f"{path}: calendar project {calendar.project!r} is not {team.project!r}")
    return {r.name: r for r in calendar.releases}


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
    """Forget cached teams (tests, and after a tenant changes a connector)."""
    _yaml_teams.cache_clear()
    with _db_lock:
        _db_cache.clear()
