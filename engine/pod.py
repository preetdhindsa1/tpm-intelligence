"""Pod facts for the AI-native PDLC page (ADR-0023 addendum 2). Pure, no I/O.

Who reviewed comes from the pod marker (addendum 1), never from the login: every agent
posts from the owner's account. Counts by lane only. No AI anywhere here.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

from engine.lab import AGENT_LANES, LaneSpec
from engine.projection import PullRequest
from engine.review_rounds import is_bot

MEMBERS = (("human", "owner"), ("claude", "agent"), ("cursor", "agent"), ("dependabot", "bot"))
MIN_MERGED = 5  # pod rule R22: no median from fewer than 5 merged PRs
MAX_OPEN_PER_AGENT = 2  # R9
MAX_LINES = 400  # R8
KEPT_WINDOW = timedelta(days=30)
# The pod rules took effect when PR #76 merged: from then on only the owner merges
# (AGENTS.md). Earlier, agents sometimes merged by pushing from the owner's account, so
# a merge by that account counts as a person's approval only from here (ADR-0023 add. 3).
POD_RULES_START = datetime(2026, 11, 24, 7, 2, 8, tzinfo=UTC)
ROUND_GAP = timedelta(minutes=60)  # one sitting, as in engine.review_rounds
_REVERTS = re.compile(r"^Reverts\s+\S+#(\d+)", re.M)


def actions(pr: PullRequest, marker_lanes: dict[str, str]) -> list[tuple[str, datetime]]:
    """Review actions as (actor, at). Actor is an agent lane (``cross-review`` marker) or
    ``human`` (unmarked, not a bot). Other agent markers (replies) are not reviews."""
    out: list[tuple[str, datetime]] = []
    items = [(r.reviewer, r.marker, r.submitted_at) for r in pr.reviews]
    items += [(c.author, c.marker, c.at) for c in pr.comments]
    for who, marker, at in items:
        kind, _, label = (marker or "").partition(":")
        if label in marker_lanes:
            if kind == "cross-review":
                out.append((marker_lanes[label], at))
        elif who and not is_bot(who):
            out.append(("human", at))
    return sorted(out, key=lambda a: a[1])


def _rounds(acts: list[tuple[str, datetime]]) -> int:
    last: dict[str, datetime] = {}
    n = 0
    for actor, at in acts:
        if actor not in last or at - last[actor] > ROUND_GAP:
            n += 1
        last[actor] = at
    return n


def _open_load(prs: list[PullRequest], lane_of: dict[str, str], lane: str) -> tuple[int, int]:
    """Most PRs of ``lane`` open at once, and how many were opened over the R9 cap."""
    marks = []
    for pr in prs:
        if lane_of[pr.key] == lane:
            marks.append((pr.created_at, 1))
            end = pr.merged_at or pr.closed_at
            if end is not None:
                marks.append((end, -1))
    best = now = over = 0
    for _, step in sorted(marks):  # a close sorts before an open at the same instant
        if step > 0 and now >= MAX_OPEN_PER_AGENT:
            over += 1
        now += step
        best = max(best, now)
    return best, over


def _median_minutes(prs: list[PullRequest]) -> int | None:
    done = [pr for pr in prs if pr.merged_at is not None]
    if len(done) < MIN_MERGED:
        return None
    return round(median((pr.merged_at - pr.created_at).total_seconds() / 60 for pr in done))  # type: ignore[operator]


def pod_facts(
    prs: list[PullRequest],
    lane_of: dict[str, str],
    rules: tuple[LaneSpec, ...] | list[LaneSpec],
    collisions: int,
    as_of: datetime,
    approvers: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """Members, the 7-stage flow, metrics vs targets and rule checks for the PRs in the window.

    ``approvers`` are the logins whose merge is a person's approval (the team's reviewer
    pool), counted from :data:`POD_RULES_START`.
    """
    marker_lanes = {label: r.name for r in rules for label in r.labels if r.name in AGENT_LANES}
    acts = {pr.key: actions(pr, marker_lanes) for pr in prs}
    people = [pr for pr in prs if lane_of[pr.key] != "dependabot"]
    merged = [pr for pr in people if pr.merged_at is not None]

    def before_merge(pr: PullRequest, who: set[str]) -> bool:
        end = pr.merged_at or as_of
        return any(actor in who and at <= end for actor, at in acts[pr.key])

    agent_merged = [pr for pr in merged if lane_of[pr.key] in AGENT_LANES]
    cross = [pr for pr in agent_merged if before_merge(pr, set(AGENT_LANES) - {lane_of[pr.key]})]
    human = [pr for pr in merged if before_merge(pr, {"human"})]
    under_rules = [
        pr for pr in merged if pr.merged_at is not None and pr.merged_at >= POD_RULES_START
    ]
    approved = [pr for pr in under_rules if pr.merged_by in set(approvers)]
    approved_keys = {pr.key for pr in approved}
    # Alone: nobody from another lane reviewed it before merge. An agent's PR that the owner
    # merged was approved by a person, so it is not alone; the owner's own PRs still need a
    # review from an agent.
    alone = [
        pr for pr in merged
        if not before_merge(pr, ({"human"} | set(AGENT_LANES)) - {lane_of[pr.key]})
        and not (lane_of[pr.key] in AGENT_LANES and pr.key in approved_keys)
    ]  # fmt: skip
    over = [
        pr for pr in people
        if pr.additions + pr.deletions > MAX_LINES and "size:exception" not in pr.labels
    ]  # fmt: skip
    load = [_open_load(prs, lane_of, lane) for lane in AGENT_LANES]
    max_open = max((m for m, _ in load), default=0)
    over_cap = sum(o for _, o in load)
    risk = [pr for pr in people if sum(lb.startswith("risk:") for lb in pr.labels) != 1]
    no_lane = [pr for pr in prs if lane_of[pr.key] == "unassigned"]
    bots = [pr for pr in prs if lane_of[pr.key] == "dependabot"]
    bot_closed = [pr for pr in bots if pr.closed_at is not None and pr.merged_at is None]
    red = [pr for pr in people if any(c.conclusion == "failure" for c in pr.checks)]
    rounds = [_rounds(acts[pr.key]) for pr in merged]
    enough = len(merged) >= MIN_MERGED

    reverted = {f"{pr.repo}#{n}" for pr in merged if pr.title.startswith('Revert "')
                for n in _REVERTS.findall(pr.body or "")}  # fmt: skip
    eligible = [pr for pr in merged if pr.merged_at and pr.merged_at <= as_of - KEPT_WINDOW]
    kept = [pr for pr in eligible if pr.key not in reverted]
    first = min((pr.merged_at for pr in merged if pr.merged_at), default=None)
    kept_reason = (
        None if eligible
        else "No merged pull request is 30 days old yet"
        + (f" (the first is on {(first + KEPT_WINDOW).date().isoformat()})" if first else "")
    )  # fmt: skip

    def stage(name: str, rules_: str, status: str, value: dict[str, Any] | None,
              reason: str | None = None) -> dict[str, Any]:  # fmt: skip
        if not people and status != "not_measured":
            status, reason = "not_measured", "No pull requests in the window yet"
        return {"stage": name, "rules": rules_, "status": status, "value": value, "reason": reason}

    def metric(name: str, target: str, value: float | None, unit: str,
               reason: str | None = None) -> dict[str, Any]:  # fmt: skip
        if value is None and reason is None:
            reason = "Not enough data yet: fewer than 5 merged pull requests"
        return {"metric": name, "target": target, "value": value, "unit": unit, "reason": reason}

    def rule(code: str, title: str, bad: int | None, of: int | None) -> dict[str, Any]:
        # A rule with nothing to check is not "held": 0 of 0 says nothing.
        status = "not_measured" if bad is None or of == 0 else "held" if bad == 0 else "broken"
        return {"rule": code, "title": title, "status": status, "count": bad, "of": of}

    median_rounds = float(median(rounds)) if enough else None
    three = round(sum(r >= 3 for r in rounds) / len(rounds), 3) if enough else None
    return {
        "members": [
            {
                "lane": lane, "kind": kind,
                "opened": sum(lane_of[pr.key] == lane for pr in prs),
                "merged": sum(lane_of[pr.key] == lane and pr.merged_at is not None for pr in prs),
                "closed_unmerged": sum(lane_of[pr.key] == lane and pr.closed_at is not None
                                       and pr.merged_at is None for pr in prs),
                "open": sum(lane_of[pr.key] == lane and pr.state == "open" for pr in prs),
                "median_minutes_to_merge": _median_minutes(
                    [pr for pr in prs if lane_of[pr.key] == lane]),
            }
            for lane, kind in MEMBERS
        ],
        "no_lane": len(no_lane),
        "flow": [
            stage("contract", "R5 R6", "not_measured", None,
                  "Issues and their acceptance tests are not collected yet"),
            stage("build", "R7 R8 R9",
                  "held" if max_open <= MAX_OPEN_PER_AGENT and not over and not collisions
                  else "broken",
                  {"max_open_per_agent": max_open, "over_400_lines": len(over),
                   "collisions": collisions}),
            stage("cross_review", "R13", "not_measured" if not agent_merged
                  else "held" if len(cross) == len(agent_merged) else "broken",
                  {"cross_reviewed": len(cross), "agent_merged": len(agent_merged)}),
            stage("ci", "R17", "held" if not red else "broken", {"failing_head_check": len(red)},
                  "Failing check on the latest commit only; run history (three red runs) is "
                  "not collected"),
            # Held when a person approved (merged) every PR since the rules started.
            stage("human_review", "R14 R15 R16", "not_measured" if not under_rules
                  else "held" if len(approved) == len(under_rules) else "broken",
                  {"human_reviewed": len(human), "merged": len(merged),
                   "approved": len(approved), "approved_of": len(under_rules)}),
            stage("merge", "R3 R21", "held" if enough else "not_measured",
                  {"median_minutes_to_merge": _median_minutes(merged)},
                  None if enough else "Not enough data yet: fewer than 5 merged pull requests"),
            stage("kept", "R21", "not_measured" if not eligible
                  else "held" if len(kept) == len(eligible) else "broken",
                  {"kept": len(kept), "eligible": len(eligible)}, kept_reason),
        ],
        "metrics": [
            metric("review_rounds_per_pr", "below 1.5", median_rounds, "rounds"),
            metric("first_pass_approval", "above 70%", None, "share",
                   "Not measurable here: GitHub does not let a PR's author approve it, and "
                   "every pull request here is opened from the owner's account"),
            metric("open_to_merge", "same day", _median_minutes(merged), "minutes"),
            metric("three_plus_rounds", "below 10%", three, "share"),
            metric("kept_rate_30d", "above 95%",
                   round(len(kept) / len(eligible), 3) if eligible else None, "share",
                   kept_reason),
            metric("human_review_load", "60-80%", None, "share", "TBD (not yet measured)"),
        ],
        "rules": [
            rule("R2", "No one approves their own work alone", len(alone), len(merged)),
            rule("R5", "Contract first", None, None),
            rule("R6", "Every PR has exactly one risk tier", len(risk), len(people)),
            rule("R8", "Small PRs, under 400 lines", len(over), len(people)),
            rule("R9", "Two open PRs per agent at most",
                 over_cap,
                 sum(lane_of[pr.key] in AGENT_LANES for pr in prs)),
            rule("R12", "Every PR says who wrote it", len(no_lane), len(prs)),
            rule("R13", "Cross-review before the human", len(agent_merged) - len(cross),
                 len(agent_merged)),
            rule("R26", "Limit bot noise", len(bot_closed), len(bots)),
        ],
    }  # fmt: skip
