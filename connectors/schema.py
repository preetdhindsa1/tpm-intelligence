"""Pydantic models for a team's connector config (ADR-0003)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GitHubPlanning(BaseModel):
    """Plan lives on GitHub issues (Kubernetes enhancements style)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["github"] = "github"
    repo: str = Field(description="owner/name of the planning issues repo")


class JiraPlanning(BaseModel):
    """Plan lives in Jira (company / Apache Kafka style). Collector not required to load config."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["jira"] = "jira"
    base_url: str
    project_key: str


class CodeRepos(BaseModel):
    """GitHub repos whose PRs/reviews/CI are the truth."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repos: tuple[str, ...] = Field(min_length=1)


class CalendarRef(BaseModel):
    """Path to a release calendar YAML (github_poller/release_calendar.yaml shape)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str


class TeamConfig(BaseModel):
    """One cross-functional team's plug-in definition.

    Adding a team should mean: write this file, pick a link pack, point a collector at it.
    No forks of engine/, api/, or pipeline/.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(description="Stable id, e.g. kubernetes or kafka")
    display_name: str
    project: str = Field(description="Prefix used in release keys, e.g. kubernetes:v1.38")
    link_pack: Literal["kep", "jira_key"] = "kep"
    planning: GitHubPlanning | JiraPlanning = Field(discriminator="source")
    code: CodeRepos
    calendar: CalendarRef

    def calendar_path(self, *, relative_to: Path) -> Path:
        """Resolve the calendar file (paths are repo-root relative unless absolute)."""
        path = Path(self.calendar.path)
        if path.is_absolute():
            return path
        # Prefer relative to repo root (parent of connectors/), then relative_to.
        repo_root = Path(__file__).resolve().parent.parent
        candidate = repo_root / path
        if candidate.is_file():
            return candidate
        return (relative_to / path).resolve()

    @property
    def primary_code_repo(self) -> str:
        """Main code repo used by the GitHub PR poller."""
        return self.code.repos[0]

    @property
    def planning_repo(self) -> str | None:
        """GitHub planning repo, if this team uses GitHub issues for the plan."""
        if isinstance(self.planning, GitHubPlanning):
            return self.planning.repo
        return None
