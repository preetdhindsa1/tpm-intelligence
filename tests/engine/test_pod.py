"""Pod facts (ADR-0023 addendum 2) on PRs shaped like this repository's (2026-11-24)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from engine.lab import LaneSpec
from engine.pod import actions, pod_facts
from engine.projection import Comment, PullRequest, Review

REPO = "preetdhindsa1/tpm-intelligence"
OWNER = "owner"  # every PR, review and comment here comes from the owner's account
T0 = datetime(2026, 11, 24, 20, tzinfo=UTC)
RULES = (
    LaneSpec("claude", ("claude-agent",), ("claude/",), ()),
    LaneSpec("cursor", ("cursor-agent",), ("cursor/",), ()),
    LaneSpec("human", ("harpreet",), ("harpreet/",), ()),
)


def pr(n: int, *, hours: float = 1, merged: bool = True, **kw: Any) -> PullRequest:
    created = T0 + timedelta(hours=n)
    base: dict[str, Any] = {
        "key": f"{REPO}#{n}", "repo": REPO, "number": n, "title": f"PR {n}", "body": "",
        "author": OWNER, "labels": ("risk:low",), "created_at": created,
        "state": "merged" if merged else "open",
        "merged_at": created + timedelta(hours=hours) if merged else None,
        "closed_at": created + timedelta(hours=hours) if merged else None,
        "reviews": (), "checks": (), "additions": 10, "deletions": 0,
    }  # fmt: skip
    return PullRequest(**{**base, **kw})


def review(n: int, body_marker: str | None, minutes: int = 10) -> Review:
    return Review(f"r{n}{minutes}", OWNER, "commented", T0 + timedelta(hours=n, minutes=minutes),
                  body_marker)  # fmt: skip


MARKERS = {"claude-agent": "claude", "cursor-agent": "cursor"}


def test_marker_says_who_reviewed_and_replies_are_not_reviews() -> None:
    p = pr(1, reviews=(review(1, "cross-review:cursor-agent"), review(1, "reply:claude-agent", 20),
                       review(1, None, 30)))  # fmt: skip
    assert [a for a, _ in actions(p, MARKERS)] == ["cursor", "human"]


def test_flow_and_rules_on_a_small_real_shaped_window() -> None:
    reviewed = pr(1, reviews=(review(1, "cross-review:cursor-agent"), review(1, None, 40)))
    alone = pr(2)  # a claude PR merged with no review: R2 and R13 broken
    big = pr(3, additions=900, labels=("risk:high", "size:exception"))  # accepted size
    over = pr(4, additions=500, labels=())  # over 400 lines and no risk tier
    bot = pr(5, merged=False, state="closed", closed_at=T0 + timedelta(hours=6))
    loose = pr(6)
    prs = [reviewed, alone, big, over, bot, loose]
    lanes = dict(zip([p.key for p in prs],
                     ["claude", "claude", "human", "cursor", "dependabot", "unassigned"],
                     strict=True))  # fmt: skip
    facts = pod_facts(prs, lanes, RULES, collisions=0, as_of=T0 + timedelta(days=1))
    flow = {s["stage"]: s for s in facts["flow"]}
    assert flow["cross_review"]["value"] == {"cross_reviewed": 1, "agent_merged": 3}
    assert flow["human_review"]["value"] == {"human_reviewed": 1, "merged": 5}
    assert flow["build"]["value"]["over_400_lines"] == 1
    assert flow["merge"]["status"] == "held"  # 5 merged: a median is allowed (R22)
    assert flow["kept"]["status"] == "not_measured"
    assert "2026-12-24" in flow["kept"]["reason"]
    rules = {r["rule"]: (r["status"], r["count"], r["of"]) for r in facts["rules"]}
    assert rules["R2"] == ("broken", 4, 5)
    assert rules["R6"] == ("broken", 1, 5)
    assert rules["R8"] == ("broken", 1, 5)
    assert rules["R12"] == ("broken", 1, 6)
    assert rules["R13"] == ("broken", 2, 3)
    assert rules["R26"] == ("broken", 1, 1)
    assert rules["R5"][0] == "not_measured"
    bot_row = next(m for m in facts["members"] if m["lane"] == "dependabot")
    assert (bot_row["opened"], bot_row["closed_unmerged"]) == (1, 1)
    claude = next(m for m in facts["members"] if m["lane"] == "claude")
    assert claude["median_minutes_to_merge"] is None  # 2 merged: not enough data
    metrics = {m["metric"]: m for m in facts["metrics"]}
    assert metrics["first_pass_approval"]["value"] is None
    assert "owner's account" in metrics["first_pass_approval"]["reason"]


def test_wip_limit_counts_open_prs_per_agent_lane() -> None:
    prs = [pr(n, hours=10) for n in (1, 2, 3)]  # three claude PRs open at once
    facts = pod_facts(prs, {p.key: "claude" for p in prs}, RULES, 0, T0 + timedelta(days=1))
    assert (
        next(s for s in facts["flow"] if s["stage"] == "build")["value"]["max_open_per_agent"] == 3
    )
    r9 = next(r for r in facts["rules"] if r["rule"] == "R9")
    assert (r9["status"], r9["count"], r9["of"]) == ("broken", 1, 3)  # the third one


def test_a_revert_within_30_days_is_not_kept() -> None:
    first = pr(1)
    revert = pr(2, title='Revert "PR 1"', body=f"Reverts {REPO}#1")
    later = T0 + timedelta(days=40)
    facts = pod_facts([first, revert], {first.key: "claude", revert.key: "human"}, RULES, 0, later)
    kept = next(s for s in facts["flow"] if s["stage"] == "kept")
    assert kept["value"] == {"kept": 1, "eligible": 2}
    assert kept["status"] == "broken"


def test_unmarked_bot_comments_are_not_reviews() -> None:
    p = pr(1, comments=(Comment("c1", "dependabot[bot]", T0 + timedelta(hours=1, minutes=5)),))
    assert actions(p, MARKERS) == []


def test_an_empty_window_is_not_measured_not_held() -> None:
    facts = pod_facts([], {}, RULES, 0, T0)
    assert {s["status"] for s in facts["flow"]} == {"not_measured"}
    assert {r["status"] for r in facts["rules"]} == {"not_measured"}
