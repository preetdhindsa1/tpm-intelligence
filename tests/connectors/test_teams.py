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
