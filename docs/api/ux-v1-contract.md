# UX v1 API contract

The JSON the UX v1 screens read. Cursor builds against these examples while Claude builds
the endpoints. Rules behind each field: ADR-0025 (Portfolio) and ADR-0023 addendum 2 (pod facts on
`GET /lab`).

Conventions for every endpoint here:

- Timestamps are ISO 8601 in UTC (`Z`). The web app converts to the viewer's time zone.
- Every number is computed by code from stored data. Text fields (`headline`, `detail`,
  `text`, `label`) are fixed templates filled with those numbers. No AI writes them.
- No usernames. Counts and roles only (CLAUDE.md section 10).
- `null` means "not known" and the page shows why. It is never a zero.

## `GET /portfolio`

All live programs at once. No query parameters. Example built from the live data on
2026-11-24 (Kubernetes v1.38, Apache Kafka 4.5.0, this repository's Phase 3).

```json
{
  "as_of": "2026-11-24T23:21:55Z",
  "totals": {
    "programs": 3,
    "planning_tools": ["github", "jira"],
    "waiting_on_you": 3
  },
  "programs": [
    {
      "key": "kubernetes:v1.38",
      "project": "kubernetes",
      "display_name": "Kubernetes",
      "release": "v1.38",
      "planning_tool": "github",
      "code_freeze_label": "Code Freeze",
      "code_tools": ["github"],
      "has_lab": false,
      "as_of": "2026-11-24T23:21:55Z",
      "dates": {
        "cycle_start_at": "2026-08-31T00:00:00Z",
        "enhancements_freeze_at": "2026-09-30T12:00:00Z",
        "code_freeze_at": "2026-11-17T12:00:00Z",
        "release_at": "2026-12-16T00:00:00Z"
      },
      "stage": {
        "current": "verify",
        "stages": [
          {"name": "plan", "status": "done"},
          {"name": "build", "status": "done"},
          {"name": "verify", "status": "current"},
          {"name": "launch", "status": "upcoming"},
          {"name": "learn", "status": "upcoming"}
        ],
        "last_milestone": {"name": "code_freeze", "at": "2026-11-17T12:00:00Z"},
        "next_milestone": {"name": "release", "at": "2026-12-16T00:00:00Z"},
        "days_to_next_milestone": 22
      },
      "scope": {"features_in_release": 70, "features_ever": 106},
      "bottleneck": {
        "kind": "critical_flags",
        "severity": "critical",
        "headline": "28 critical flags",
        "detail": "25 features past Code Freeze with the main PR not merged",
        "facts": {
          "critical_features": 28,
          "top_flag": "main_pr_not_merged",
          "top_flag_features": 25
        }
      },
      "next_decision": {
        "kind": "approve_exec_update",
        "label": "Approve exec update",
        "count": 1,
        "ref": {"update_id": 2}
      }
    },
    {
      "key": "tpm-intelligence:Phase 3",
      "project": "tpm-intelligence",
      "display_name": "Program Intelligence Platform (Current Project)",
      "release": "Phase 3",
      "planning_tool": "github",
      "code_freeze_label": "Code Freeze",
      "code_tools": ["github"],
      "has_lab": true,
      "as_of": "2026-11-24T23:21:55Z",
      "dates": {
        "cycle_start_at": "2026-11-30T00:00:00Z",
        "enhancements_freeze_at": "2026-12-14T12:00:00Z",
        "code_freeze_at": "2027-01-14T12:00:00Z",
        "release_at": "2027-01-20T00:00:00Z"
      },
      "stage": {
        "current": "plan",
        "stages": [
          {"name": "plan", "status": "current"},
          {"name": "build", "status": "upcoming"},
          {"name": "verify", "status": "upcoming"},
          {"name": "launch", "status": "upcoming"},
          {"name": "learn", "status": "upcoming"}
        ],
        "last_milestone": null,
        "next_milestone": {"name": "cycle_start", "at": "2026-11-30T00:00:00Z"},
        "days_to_next_milestone": 6
      },
      "scope": {"features_in_release": 4, "features_ever": 4},
      "bottleneck": {
        "kind": "review_gap",
        "severity": "warning",
        "headline": "Review gap",
        "detail": "47 pull requests merged, 0 with a human review",
        "facts": {"merged": 47, "approved_merged": 0, "median_minutes_to_merge": 9, "human_reviewed": 0, "reviewed_of": 47}
      },
      "next_decision": {
        "kind": "classify_prs",
        "label": "Classify pull requests with no lane",
        "count": 2,
        "ref": null
      }
    },
    {
      "key": "KAFKA:4.5.0",
      "project": "KAFKA",
      "display_name": "Apache Kafka",
      "release": "4.5.0",
      "planning_tool": "jira",
      "code_freeze_label": "Feature Freeze",
      "code_tools": ["github"],
      "has_lab": false,
      "as_of": "2026-11-24T23:21:55Z",
      "dates": {
        "cycle_start_at": "2026-10-26T00:00:00Z",
        "enhancements_freeze_at": "2027-01-14T00:00:00Z",
        "code_freeze_at": "2027-02-04T00:00:00Z",
        "release_at": "2027-03-17T00:00:00Z"
      },
      "stage": {
        "current": "build",
        "stages": [
          {"name": "plan", "status": "done"},
          {"name": "build", "status": "current"},
          {"name": "verify", "status": "upcoming"},
          {"name": "launch", "status": "upcoming"},
          {"name": "learn", "status": "upcoming"}
        ],
        "last_milestone": {"name": "cycle_start", "at": "2026-10-26T00:00:00Z"},
        "next_milestone": {"name": "enhancements_freeze", "at": "2027-01-14T00:00:00Z"},
        "days_to_next_milestone": 51
      },
      "scope": {"features_in_release": 16, "features_ever": 18},
      "bottleneck": {
        "kind": "linking_gap",
        "severity": "warning",
        "headline": "3 of 16 features have no linked code",
        "detail": "13 of 16 features in the release are linked to a pull request",
        "facts": {"features_in_release": 16, "linked_features": 13, "unlinked_features": 3}
      },
      "next_decision": null
    }
  ],
  "waiting_on_you": [
    {
      "kind": "approve_exec_update",
      "program_key": "kubernetes:v1.38",
      "label": "Kubernetes v1.38 exec update · draft",
      "count": 1,
      "ref": {"update_id": 2}
    },
    {
      "kind": "review_link_suggestions",
      "program_key": "kubernetes:v1.38",
      "label": "101 AI link suggestions · v1.38",
      "count": 101,
      "ref": null
    },
    {
      "kind": "classify_prs",
      "program_key": "tpm-intelligence:Phase 3",
      "label": "2 pull requests with no lane · Program Intelligence Platform (Current Project)",
      "count": 2,
      "ref": null
    }
  ],
  "across_programs": [
    {
      "kind": "late_code",
      "title": "Code lands late, not never",
      "text": "Kubernetes v1.38: 17 features were removed at the freeze and later re-added.",
      "program_key": "kubernetes:v1.38",
      "facts": {"readded_after_freeze": 17}
    },
    {
      "kind": "review_gap",
      "title": "Review is the new bottleneck",
      "text": "Program Intelligence Platform (Current Project): pull requests merge in a median of 9 minutes, and 0 of 47 had a human review.",
      "program_key": "tpm-intelligence:Phase 3",
      "facts": {"merged": 47, "approved_merged": 0, "median_minutes_to_merge": 9, "human_reviewed": 0, "reviewed_of": 47}
    },
    {
      "kind": "unlinked_load",
      "title": "Unlinked work is real load",
      "text": "1,173 open Kubernetes pull requests are not linked to any feature but still use the same reviewers.",
      "program_key": "kubernetes:v1.38",
      "facts": {"unlinked_open_prs": 1173}
    }
  ],
  "coming_next": [
    {"module": "raid", "name": "RAID tracker", "status": "planned"},
    {"module": "readiness", "name": "Release readiness", "status": "planned"},
    {"module": "retro", "name": "Retro insights", "status": "planned"}
  ],
  "skipped": []
}
```

### Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `as_of` | timestamp | The oldest `as_of` of any program below. The page shows "data as of" from it. |
| `totals.programs` | int | Length of `programs`. |
| `totals.planning_tools` | string[] | Distinct `planning_tool` values, sorted. |
| `totals.waiting_on_you` | int | Length of `waiting_on_you`. |
| `programs[]` | object | One per team in `connectors/teams/`, for its current release (ADR-0025 rule 1). Sorted by `dates.release_at`, then `key`. |
| `programs[].key` | string | Release key. Use `release` (and `project`) for URLs, as the existing pages do. |
| `programs[].planning_tool` | `github` \| `jira` | From the team connector's `planning.source`. |
| `programs[].code_tools` | string[] | Where code activity comes from (`github` today). |
| `programs[].has_lab` | bool | The team has agent lanes; the AI-native PDLC page has data for it. |
| `programs[].dates.*` | timestamp \| null | The release calendar. Any may be null. |
| `stage.current` | `plan` \| `build` \| `freeze` \| `launch` \| `learn` \| null | ADR-0025 rule 2. Null when a needed date is missing. |
| `stage.stages[]` | 5 objects | Always five, in order. `status`: `done` \| `current` \| `upcoming`. All `upcoming` when `current` is null. |
| `stage.last_milestone`, `stage.next_milestone` | `{name, at}` \| null | Names: `cycle_start`, `enhancements_freeze`, `code_freeze`, `release`, `launch_end`. |
| `stage.days_to_next_milestone` | int \| null | Calendar days in UTC from `as_of` to `next_milestone.at`. |
| `scope` | object | Features in the release now, and ever in it (removed ones included). |
| `bottleneck` | object | ADR-0025 rule 4. `kind`: `critical_flags` \| `review_gap` \| `linking_gap` \| `unlinked_load` \| `none`. `severity`: `critical` \| `warning` \| `info`. `facts` keys depend on `kind`, as in the example. `none` has `headline` "No bottleneck flagged", `detail` null, `facts` {}. |
| `next_decision` | object \| null | ADR-0025 rule 5. Null means nothing waits on a person for this program. |
| `next_decision.kind`, `waiting_on_you[].kind` | string | `approve_exec_update` (ref has `update_id`), `review_link_suggestions`, `classify_prs`. |
| `waiting_on_you[]` | object | Everything a person must act on, across programs, in that kind order, then by program order. |
| `across_programs[]` | object | ADR-0025 rule 7. `kind`: `late_code` \| `review_gap` \| `unlinked_load`. Present only when its fact is above zero. `unlinked_open_prs` counts distinct pull requests, not per-SIG load (`GET /releases/{name}/load` has that). |
| `coming_next[]` | object | Planned modules. `status` is `planned`. They carry no numbers. |
| `skipped[]` | `{team, reason}` | What could not be read. Reasons: `no release yet` and `release could not be computed` (the team has no row in `programs`); `exec updates could not be read` and `link suggestions could not be read` (the team **keeps** its row, and its waiting items may be incomplete). One team can appear in both `programs` and `skipped`: show the row and the note, never drop the row. |

### Where each example number comes from (2026-11-24)

| Number | Source |
| --- | --- |
| 70, 106; 16, 18; 4, 4 | `GET /releases` `features_in_release`, `features_ever_in_release` |
| 28 critical, 25 `main_pr_not_merged` | `GET /releases/v1.38/features`: in-release features with a critical flag, and the most common critical flag code among them |
| 13 of 16 linked | `GET /releases/4.5.0/features`: in-release features with `prs_total > 0` |
| 47 merged, 0 with a human review, 9 minutes | `GET /lab`: pod `human_review` stage (`human_reviewed`, `merged`) when the team has pod facts, else `n_merged` and `approved_merged`; `median_hours_to_merge` (0.156 h). ADR-0025 addendum 2 |
| Draft update 2 | `GET /releases/v1.38/updates`: the newest update has `status: draft` |
| 101 suggestions | `GET /releases/v1.38/link-suggestions`: `counts.suggested` |
| 2 with no lane | `GET /lab`: bucket `unassigned` |
| 17 re-added | `GET /releases/v1.38/summary`: `outcomes.readded_after_freeze` |
| 1,173 unlinked | Distinct open PRs with no verified link (`GET /releases/v1.38/summary` `unlinked_open_prs`). Measured on the local database on 2026-11-25, where the old per-SIG sum was 1,956: a PR with two SIG labels counted twice. The cloud value updates after deploy. |

The live numbers will move as data arrives. The shape will not change without a new
version of this file.

### Errors

- `200` with an empty `programs` list when no team has a release.
- A team whose release fails to compute is listed in `skipped` with a reason. The rest
  still return.
- If the exec updates or link suggestions store cannot be read, the program still returns,
  with a `skipped` entry naming the store, so the page can say its approvals may be missing.

## `GET /lab`: pod facts (`pod`)

`GET /lab?project=tpm-intelligence` keeps every existing field and adds `pod` (ADR-0023
addendum 2). `pod` is `null` for teams without agent lanes (Kubernetes, Kafka). The window
is the team's whole history for this repository, as for the rest of `/lab`.

Example: this repository on 2026-11-25 (68 pull requests, 53 merged), computed from its
GitHub pull requests, reviews and comments through the same normalizers the webhook
receiver uses. That sample did not fetch CI check runs, so `failing_head_check` reads 0
here by omission. The stored data has them.

```json
{
  "members": [
    {"lane": "human", "kind": "owner", "opened": 12, "merged": 12, "closed_unmerged": 0, "open": 0, "median_minutes_to_merge": 5},
    {"lane": "claude", "kind": "agent", "opened": 34, "merged": 33, "closed_unmerged": 0, "open": 1, "median_minutes_to_merge": 11},
    {"lane": "cursor", "kind": "agent", "opened": 7, "merged": 5, "closed_unmerged": 1, "open": 1, "median_minutes_to_merge": 14},
    {"lane": "dependabot", "kind": "bot", "opened": 13, "merged": 1, "closed_unmerged": 12, "open": 0, "median_minutes_to_merge": null}
  ],
  "no_lane": 2,
  "flow": [
    {"stage": "contract", "rules": "R5 R6", "status": "not_measured", "value": null, "reason": "Issues and their acceptance tests are not collected yet"},
    {"stage": "build", "rules": "R7 R8 R9", "status": "broken", "value": {"max_open_per_agent": 4, "over_400_lines": 6, "collisions": 0}, "reason": null},
    {"stage": "cross_review", "rules": "R13", "status": "broken", "value": {"cross_reviewed": 6, "agent_merged": 38}, "reason": null},
    {"stage": "ci", "rules": "R17", "status": "held", "value": {"failing_head_check": 0}, "reason": "Failing check on the latest commit only; run history (three red runs) is not collected"},
    {"stage": "human_review", "rules": "R14 R15 R16", "status": "broken", "value": {"human_reviewed": 11, "merged": 52}, "reason": null},
    {"stage": "merge", "rules": "R3 R21", "status": "held", "value": {"median_minutes_to_merge": 11}, "reason": null},
    {"stage": "kept", "rules": "R21", "status": "not_measured", "value": {"kept": 0, "eligible": 0}, "reason": "No merged pull request is 30 days old yet (the first is on 2026-12-22)"}
  ],
  "metrics": [
    {"metric": "review_rounds_per_pr", "target": "below 1.5", "value": 0.0, "unit": "rounds", "reason": null},
    {"metric": "first_pass_approval", "target": "above 70%", "value": null, "unit": "share", "reason": "Not measurable here: GitHub does not let a PR's author approve it, and every pull request here is opened from the owner's account"},
    {"metric": "open_to_merge", "target": "same day", "value": 11, "unit": "minutes", "reason": null},
    {"metric": "three_plus_rounds", "target": "below 10%", "value": 0.0, "unit": "share", "reason": null},
    {"metric": "kept_rate_30d", "target": "above 95%", "value": null, "unit": "share", "reason": "No merged pull request is 30 days old yet (the first is on 2026-12-22)"},
    {"metric": "human_review_load", "target": "60-80%", "value": null, "unit": "share", "reason": "TBD (not yet measured)"}
  ],
  "rules": [
    {"rule": "R2", "title": "No one approves their own work alone", "status": "broken", "count": 40, "of": 52},
    {"rule": "R5", "title": "Contract first", "status": "not_measured", "count": null, "of": null},
    {"rule": "R6", "title": "Every PR has exactly one risk tier", "status": "broken", "count": 48, "of": 55},
    {"rule": "R8", "title": "Small PRs, under 400 lines", "status": "broken", "count": 6, "of": 55},
    {"rule": "R9", "title": "Two open PRs per agent at most", "status": "broken", "count": 5, "of": 41},
    {"rule": "R12", "title": "Every PR says who wrote it", "status": "broken", "count": 2, "of": 68},
    {"rule": "R13", "title": "Cross-review before the human", "status": "broken", "count": 32, "of": 38},
    {"rule": "R26", "title": "Limit bot noise", "status": "broken", "count": 12, "of": 13}
  ]
}
```

### Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `members[]` | object | Always 4, in this order: `human` (owner), `claude`, `cursor` (agents), `dependabot` (bot). Counts of PRs opened, merged, closed unmerged, and open. `median_minutes_to_merge` is null below 5 merged PRs in that lane (R22). |
| `no_lane` | int | PRs that match no lane and are not Dependabot (R12). |
| `flow[]` | object | Always 7, in order: `contract`, `build`, `cross_review`, `ci`, `human_review`, `merge`, `kept`. `status`: `held` \| `broken` \| `not_measured`. `value` keys depend on the stage, as in the example; `null` for `contract`. `reason` says why a stage is not measured, or what it cannot see. |
| `metrics[]` | object | Always 6: `review_rounds_per_pr`, `first_pass_approval`, `open_to_merge`, `three_plus_rounds`, `kept_rate_30d`, `human_review_load`. `value` null means not known, and `reason` says why ("Not enough data yet", "TBD (not yet measured)", or why it cannot be measured). Shares are 0 to 1. |
| `rules[]` | object | Always 8: R2, R5, R6, R8, R9, R12, R13, R26. `count` = PRs that break the rule; `of` = PRs it applies to. R9 counts agent PRs opened while their lane already had 2 open. `not_measured` when there is nothing to check (`of` is 0) or no data (R5). |

Who reviewed is read from the pod marker (ADR-0023 addendum 1), never from the login. An
agent review is a `Cross-review · <lane>` marker. Any unmarked review or comment that is
not from a bot counts as a human review. So an agent reply without a marker is counted
as human: the page should say so next to the human-review numbers.
