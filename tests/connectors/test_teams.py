"""Team connector YAML loads and resolves calendars / link packs."""

from __future__ import annotations

from pathlib import Path

from collectors.github_poller.calendar import load_calendar
from connectors import load_team, load_teams
from connectors.load import clear_team_cache, display_name_for_project, link_pack_for_project
from linker.packs import get_pack


def setup_function() -> None:
    clear_team_cache()


def test_kubernetes_team_matches_live_example() -> None:
    team = load_team("kubernetes")
    assert team.display_name == "Kubernetes"
    assert team.project == "kubernetes"
    assert team.link_pack == "kep"
    assert team.planning_repo == "kubernetes/enhancements"
    assert team.primary_code_repo == "kubernetes/kubernetes"
    cal = load_calendar(team.calendar_path(relative_to=Path.cwd()))
    assert cal.project == "kubernetes"
    assert cal.get("v1.38").code_freeze.year == 2026


def test_kafka_team_is_jira_shaped() -> None:
    team = load_team("kafka")
    assert team.planning.source == "jira"
    assert team.link_pack == "jira_key"
    assert team.planning_repo is None
    assert team.primary_code_repo == "apache/kafka"
    assert team.code_freeze_label == "Feature Freeze"  # Kafka's name for the engine's Code Freeze
    assert load_team("kubernetes").code_freeze_label == "Code Freeze"  # the default


def test_load_teams_indexes_examples() -> None:
    teams = load_teams()
    assert set(teams) >= {"kubernetes", "kafka"}
    assert display_name_for_project("kubernetes") == "Kubernetes"
    assert display_name_for_project("KAFKA") == "Apache Kafka"
    assert link_pack_for_project("kubernetes") == "kep"
    assert link_pack_for_project("KAFKA") == "jira_key"
    assert link_pack_for_project("unknown") == "kep"


def test_kep_and_jira_packs_are_registered() -> None:
    assert get_pack("kep").name == "kep"
    assert get_pack("jira_key").name == "jira_key"


def test_this_project_tracks_itself_in_one_repo() -> None:
    """ADR-0020: real data from this repository, under its own project key."""
    from collectors.github_poller.calendar import load_calendar

    team = load_team("tpm-intelligence")
    assert team.project == "tpm-intelligence"
    assert team.link_pack == "github_issue"
    assert team.planning_repo == team.primary_code_repo == "preetdhindsa1/tpm-intelligence"
    assert team.owns("preetdhindsa1/tpm-intelligence#5")
    assert team.owns("tpm-intelligence:Paltform Intelligence Release")
    assert not team.owns("kubernetes/kubernetes#5")
    calendar = load_calendar(team.calendar_path(relative_to=Path.cwd()))
    assert calendar.get("Paltform Intelligence Release").code_freeze.isoformat() == "2026-08-14T12:00:00+00:00"
    assert get_pack("github_issue").name == "github_issue"
    assert tuple(team.author_lanes) == ("claude", "cursor", "human")
    assert team.author_lanes["cursor"].labels == ("cursor-agent",)
    assert team.author_lanes["claude"].branch_prefixes == ("claude/",)
    assert team.author_lanes["human"].labels == ("harpreet",)
    assert team.reviewer_pool == ("preetdhindsa1",)


def test_kubernetes_has_no_lanes() -> None:
    """Kubernetes is not this repository's development lab."""
    assert load_team("kubernetes").author_lanes == {}
    assert load_team("kubernetes").reviewer_pool == ()


def test_front_page_card_uses_this_projects_display_name() -> None:
    """The front page marks the card live by exact display name (web/lib/teams.ts)."""
    from pathlib import Path

    from connectors import load_team

    name = load_team("tpm-intelligence").display_name
    assert name == "Program Intelligence Platform (Current Project)"
    teams_ts = Path(__file__).parents[2] / "web" / "lib" / "teams.ts"
    assert f'SELF_PROJECT = "{name}"' in teams_ts.read_text()
