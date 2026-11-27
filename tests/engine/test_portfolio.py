"""Portfolio rules (ADR-0025) on the real calendars and counts of 2026-11-24."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from engine.portfolio import LabFacts, ProgramFacts, portfolio, program, stage


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, sec: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, sec, tzinfo=UTC)


def cal(start: datetime, ef: datetime, cf: datetime, rel: datetime) -> dict[str, Any]:
    return dict(zip(("cycle_start_at", "enhancements_freeze_at", "code_freeze_at", "release_at"),
                    (start, ef, cf, rel), strict=True))  # fmt: skip


NOW = utc(2026, 11, 24, 23, 21, 55)
V138 = cal(utc(2026, 8, 31), utc(2026, 9, 30, 12), utc(2026, 11, 17, 12), utc(2026, 12, 16))


def facts(key: str, name: str, **kw: Any) -> ProgramFacts:
    base: dict[str, Any] = {
        "project": key.split(":")[0], "display_name": name, "release": key.split(":")[1],
        "planning_tool": "github", "code_tools": ("github",), "as_of": NOW, "dates": V138,
        "critical_codes": (), "readded_after_freeze": 0, "unlinked_open_prs": 0,
    }  # fmt: skip
    return ProgramFacts(key=key, **{**base, **kw})


# Live counts on 2026-11-24: 25 features with main_pr_not_merged, 17 with removed_at_freeze.
K = facts("kubernetes:v1.38", "Kubernetes", features_in_release=70, features_ever=106,
          critical_codes=(("main_pr_not_merged",),) * 11
          + (("main_pr_not_merged", "removed_at_freeze"),) * 14 + (("removed_at_freeze",),) * 3,
          linked_features=69, readded_after_freeze=17, unlinked_open_prs=1173,
          draft_update_id=2, suggested_links=101)  # fmt: skip
KAFKA = facts("KAFKA:4.5.0", "Apache Kafka", planning_tool="jira",
              dates=cal(utc(2026, 10, 26), utc(2027, 1, 14), utc(2027, 2, 4), utc(2027, 3, 17)),
              features_in_release=16, features_ever=18, linked_features=13)  # fmt: skip
REPO = facts("tpm-intelligence:Phase 3", "Program Intelligence Platform (Current Project)",
             dates=cal(utc(2026, 11, 30), utc(2026, 12, 14, 12), utc(2027, 1, 14, 12),
                       utc(2027, 1, 20)),
             features_in_release=4, features_ever=4, linked_features=3,
             lab=LabFacts(merged=47, approved_merged=0, median_hours_to_merge=0.15583,
                          unassigned=2))  # fmt: skip


def test_v138_stage_flips_at_code_freeze_noon_utc() -> None:
    freeze = V138["code_freeze_at"]
    assert stage(V138, freeze - timedelta(seconds=1))["current"] == "build"
    at = stage(V138, freeze)
    assert at["current"] == "verify"
    assert at["last_milestone"] == {"name": "code_freeze", "at": freeze}
    statuses = [s["status"] for s in at["stages"]]
    assert statuses == ["done", "done", "current", "upcoming", "upcoming"]


def test_v138_on_2026_11_24_is_22_days_from_release() -> None:
    st = stage(V138, NOW)
    assert st["next_milestone"] == {"name": "release", "at": utc(2026, 12, 16)}
    assert st["days_to_next_milestone"] == 22


def test_launch_window_then_learn() -> None:
    assert stage(V138, utc(2026, 12, 16))["current"] == "launch"
    assert stage(V138, utc(2026, 12, 22, 23))["current"] == "launch"
    learn = stage(V138, utc(2026, 12, 23))
    assert learn["current"] == "learn"
    assert learn["next_milestone"] is None
    assert learn["days_to_next_milestone"] is None


def test_missing_code_freeze_is_stage_unknown_not_a_guess() -> None:
    st = stage({**V138, "code_freeze_at": None}, NOW)
    assert st["current"] is None
    assert {s["status"] for s in st["stages"]} == {"upcoming"}


def test_kubernetes_critical_flags_name_the_most_common_code() -> None:
    row = program(K)
    assert row["bottleneck"]["headline"] == "28 critical flags"
    assert row["bottleneck"]["detail"] == "25 features past Code Freeze with the main PR not merged"
    assert row["bottleneck"]["facts"] == {
        "critical_features": 28, "top_flag": "main_pr_not_merged", "top_flag_features": 25
    }  # fmt: skip
    assert row["next_decision"]["ref"] == {"update_id": 2}
    assert "program_key" not in row["next_decision"]


def test_the_bottleneck_uses_the_teams_name_for_its_freeze_date() -> None:
    kafka_flags = facts("KAFKA:4.4.0", "Apache Kafka", code_freeze_label="Feature Freeze",
                        critical_codes=(("main_pr_not_merged",),) * 3, features_in_release=16,
                        features_ever=18, linked_features=13)  # fmt: skip
    row = program(kafka_flags)
    assert row["code_freeze_label"] == "Feature Freeze"
    detail = row["bottleneck"]["detail"]
    assert detail == "3 features past Feature Freeze with the main PR not merged"
    assert program(K)["code_freeze_label"] == "Code Freeze"


def test_kafka_before_freeze_shows_the_linking_gap() -> None:
    row = program(KAFKA)
    assert row["stage"]["current"] == "build"
    assert row["stage"]["next_milestone"]["name"] == "enhancements_freeze"
    assert row["stage"]["days_to_next_milestone"] == 51
    assert row["bottleneck"]["headline"] == "3 of 16 features have no linked code"
    assert row["next_decision"] is None


def test_repo_in_plan_shows_the_review_gap_not_linking() -> None:
    row = program(REPO)
    assert row["stage"]["current"] == "plan"
    assert row["stage"]["last_milestone"] is None
    assert row["bottleneck"]["kind"] == "review_gap"
    assert row["bottleneck"]["facts"]["median_minutes_to_merge"] == 9
    assert row["next_decision"]["kind"] == "classify_prs"


def test_review_gap_counts_human_reviews_when_the_pod_facts_have_them() -> None:
    # Live shape on 2026-11-25: 78 merged (Dependabot included), 0 approvals because every PR
    # and review comes from one account; the pod facts count 19 of 74 people PRs reviewed.
    lab = LabFacts(merged=78, approved_merged=0, median_hours_to_merge=0.233, unassigned=2,
                   human_reviewed=19, reviewed_of=74)  # fmt: skip
    repo = facts("tpm-intelligence:Phase 3", "Program Intelligence Platform (Current Project)",
                 dates=REPO.dates, features_in_release=4, features_ever=4, linked_features=3,
                 lab=lab)  # fmt: skip
    row = program(repo)
    assert row["bottleneck"]["kind"] == "review_gap"
    assert row["bottleneck"]["detail"] == "74 pull requests merged, 19 with a human review"
    assert row["bottleneck"]["facts"]["human_reviewed"] == 19
    [gap] = [a for a in portfolio([repo], [], NOW)["across_programs"] if a["kind"] == "review_gap"]
    assert gap["text"] == (
        "Program Intelligence Platform (Current Project): pull requests merge in a median of "
        "14 minutes, and 19 of 74 had a human review."
    )


def test_review_gap_says_the_human_approved_at_merge() -> None:
    """Owner report 2026-11-25: the human merges, and so approves, every PR here."""
    lab = LabFacts(merged=90, approved_merged=88, median_hours_to_merge=0.233, unassigned=0,
                   human_reviewed=20, reviewed_of=88, human_approved=88)  # fmt: skip
    repo = facts("tpm-intelligence:Phase 3", "Program Intelligence Platform (Current Project)",
                 dates=REPO.dates, features_in_release=4, features_ever=4, linked_features=3,
                 lab=lab)  # fmt: skip
    row = program(repo)
    assert row["bottleneck"]["detail"] == (
        "88 pull requests merged, 88 approved by the human at merge, 20 with a written human review"
    )
    assert row["bottleneck"]["facts"]["human_approved"] == 88
    [gap] = [a for a in portfolio([repo], [], NOW)["across_programs"] if a["kind"] == "review_gap"]
    assert gap["text"] == (
        "Program Intelligence Platform (Current Project): pull requests merge in a median of "
        "14 minutes, and 88 of 88 were approved by the human at merge and 20 had a written "
        "human review."
    )


def test_no_review_gap_when_most_prs_had_a_human_review() -> None:
    lab = LabFacts(merged=78, approved_merged=0, median_hours_to_merge=0.233, unassigned=0,
                   human_reviewed=40, reviewed_of=74)  # fmt: skip
    repo = facts("tpm-intelligence:Phase 3", "x", dates=REPO.dates, features_in_release=4,
                 features_ever=4, linked_features=4, lab=lab)  # fmt: skip
    assert program(repo)["bottleneck"]["kind"] != "review_gap"


def test_review_gap_needs_five_merged_prs() -> None:
    small = facts("tpm-intelligence:Phase 3", "x", dates=REPO.dates, features_in_release=4,
                  features_ever=4, linked_features=3, lab=LabFacts(4, 0, 0.1, 0))  # fmt: skip
    assert program(small)["bottleneck"]["kind"] == "none"


def test_whole_portfolio_matches_the_contract_example() -> None:
    body = portfolio([REPO, KAFKA, K], [], NOW)
    keys = [p["key"] for p in body["programs"]]
    assert keys == ["kubernetes:v1.38", "tpm-intelligence:Phase 3", "KAFKA:4.5.0"]
    assert body["totals"] == {
        "programs": 3, "planning_tools": ["github", "jira"], "waiting_on_you": 3
    }  # fmt: skip
    waiting = [(i["kind"], i["count"]) for i in body["waiting_on_you"]]
    assert waiting == [("approve_exec_update", 1), ("review_link_suggestions", 101),
                       ("classify_prs", 2)]  # fmt: skip
    kinds = [a["kind"] for a in body["across_programs"]]
    assert kinds == ["late_code", "review_gap", "unlinked_load"]
    assert body["across_programs"][1]["text"] == (
        "Program Intelligence Platform (Current Project): pull requests merge in a median of "
        "9 minutes, and 0 of 47 had an approving review."
    )
    assert body["across_programs"][2]["text"].startswith("1,173 open Kubernetes pull requests")
    assert all(m["status"] == "planned" for m in body["coming_next"])


def test_empty_portfolio() -> None:
    body = portfolio([], [{"team": "kafka", "reason": "no release yet"}], NOW)
    assert body["programs"] == []
    assert body["as_of"] == NOW
    assert body["totals"]["waiting_on_you"] == 0


def test_raid_items_waiting_come_after_link_suggestions() -> None:
    from dataclasses import replace

    body = portfolio([replace(K, raid_suggested=1)], [], NOW, frozenset({"raid"}))
    assert [i["kind"] for i in body["waiting_on_you"]] == [
        "approve_exec_update", "review_link_suggestions", "review_raid",
    ]  # fmt: skip
    assert body["waiting_on_you"][2]["label"] == "1 RAID item waiting for review · v1.38"
    assert [m["status"] for m in body["coming_next"]] == ["live", "planned", "planned"]


def test_raid_alone_is_the_next_decision() -> None:
    from dataclasses import replace

    row = program(replace(KAFKA, raid_suggested=4))
    assert row["next_decision"] == {"kind": "review_raid", "label": "Review RAID items",
                                    "count": 4, "ref": None}  # fmt: skip


def test_coming_next_carries_validation_only_for_modelled_modules() -> None:
    from engine.portfolio import coming_next

    rows = coming_next(frozenset({"readiness"}), {"readiness": False})
    assert [(m["module"], m["status"], m["validated"]) for m in rows] == [
        ("raid", "planned", None), ("readiness", "live", False), ("retro", "planned", None),
    ]  # fmt: skip


def test_has_retro_is_on_the_row() -> None:
    from dataclasses import replace

    assert program(replace(K, has_retro=True))["has_retro"] is True
    assert program(K)["has_retro"] is False
