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


class LaneRule(BaseModel):
    """One author lane. First match wins: label, then branch, then trailer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    labels: tuple[str, ...] = ()
    branch_prefixes: tuple[str, ...] = ()
    trailers: tuple[str, ...] = ()


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
    link_pack: Literal["kep", "jira_key", "github_issue"] = "kep"
    planning: GitHubPlanning | JiraPlanning = Field(discriminator="source")
    code: CodeRepos
    calendar: CalendarRef
    # Empty means this team has no development lab. Match order is label, then branch
    # prefix, then trailer (engine/lab.py). Dict order is the lane order.
    author_lanes: dict[str, LaneRule] = Field(default_factory=dict)
    reviewer_pool: tuple[str, ...] = ()

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

    def owns(self, subject_key: str) -> bool:
        """Whether an event subject belongs to this team (ADR-0018: one world per project).

        Release keys start with ``<project>:``; work items with the planning repo
        (``kubernetes/enhancements#``) or Jira project key (``KAFKA-``); pull requests with
        one of the code repos (``apache/kafka#``).
        """
        if subject_key.startswith(f"{self.project}:"):
            return True
        if isinstance(self.planning, GitHubPlanning):
            prefixes = [f"{self.planning.repo}#"]
        else:
            prefixes = [f"{self.planning.project_key}-"]
        prefixes += [f"{repo}#" for repo in self.code.repos]
        return subject_key.startswith(tuple(prefixes))

    @property
    def planning_repo(self) -> str | None:
        """GitHub planning repo, if this team uses GitHub issues for the plan."""
        if isinstance(self.planning, GitHubPlanning):
            return self.planning.repo
        return None
