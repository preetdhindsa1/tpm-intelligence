# UX v1 API contract

The JSON the UX v1 screens read. Cursor builds against these examples while Claude builds
the endpoints. Rules behind each field: ADR-0025 (Portfolio). The pod facts on `GET /lab`
are added to this file by issue #94.

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
        "current": "freeze",
        "stages": [
          {"name": "plan", "status": "done"},
          {"name": "build", "status": "done"},
          {"name": "freeze", "status": "current"},
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
      "key": "KAFKA:4.5.0",
      "project": "KAFKA",
      "display_name": "Apache Kafka",
      "release": "4.5.0",
      "planning_tool": "jira",
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
          {"name": "freeze", "status": "upcoming"},
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
    },
    {
      "key": "tpm-intelligence:Phase 3",
      "project": "tpm-intelligence",
      "display_name": "Program Intelligence Platform (this project)",
      "release": "Phase 3",
      "planning_tool": "github",
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
          {"name": "freeze", "status": "upcoming"},
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
        "detail": "47 pull requests merged, 0 with an approving review",
        "facts": {"merged": 47, "approved_merged": 0, "median_minutes_to_merge": 9}
      },
      "next_decision": {
        "kind": "classify_prs",
        "label": "Classify pull requests with no lane",
        "count": 2,
        "ref": null
      }
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
      "label": "2 pull requests in this repo with no lane",
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
      "text": "This repo: pull requests merge in a median of 9 minutes, and 0 of 47 had an approving review.",
      "program_key": "tpm-intelligence:Phase 3",
      "facts": {"merged": 47, "approved_merged": 0, "median_minutes_to_merge": 9}
    },
    {
      "kind": "unlinked_load",
      "title": "Unlinked work is real load",
      "text": "1,978 open Kubernetes pull requests are not linked to any feature but still use the same reviewers.",
      "program_key": "kubernetes:v1.38",
      "facts": {"unlinked_open_prs": 1978}
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
| `across_programs[]` | object | ADR-0025 rule 7. `kind`: `late_code` \| `review_gap` \| `unlinked_load`. Present only when its fact is above zero. |
| `coming_next[]` | object | Planned modules. `status` is `planned`. They carry no numbers. |
| `skipped[]` | `{team, reason}` | Teams with no release yet, or whose release could not be computed. The page may list them. |

### Where each example number comes from (2026-11-24)

| Number | Source |
| --- | --- |
| 70, 106; 16, 18; 4, 4 | `GET /releases` `features_in_release`, `features_ever_in_release` |
| 28 critical, 25 `main_pr_not_merged` | `GET /releases/v1.38/features`: in-release features with a critical flag, and the most common critical flag code among them |
| 13 of 16 linked | `GET /releases/4.5.0/features`: in-release features with `prs_total > 0` |
| 47 merged, 0 approved, 9 minutes | `GET /lab`: `n_merged`, `approved_merged`, `median_hours_to_merge` (0.156 h) |
| Draft update 2 | `GET /releases/v1.38/updates`: the newest update has `status: draft` |
| 101 suggestions | `GET /releases/v1.38/link-suggestions`: `counts.suggested` |
| 2 with no lane | `GET /lab`: bucket `unassigned` |
| 17 re-added | `GET /releases/v1.38/summary`: `outcomes.readded_after_freeze` |
| 1,978 unlinked | `GET /releases/v1.38/summary`: `unlinked_open_prs` |

The live numbers will move as data arrives. The shape will not change without a new
version of this file.

### Errors

- `200` with an empty `programs` list when no team has a release.
- A team whose release fails to compute is listed in `skipped` with a reason. The rest
  still return.
