# Release readiness and retro API contract (v1)

Wave 5 (docs/plan/e2e-plan.md), ADR-0032. Written before the readiness and retro pages, so
cursor-agent can build them in parallel. Every example below comes from the API's synthetic
fixture and is checked by `tests/api/test_readiness.py`.

## Rules the pages can rely on

- **Synthetic until the engines land.** Until #181 (readiness) and #182 (retro facts), every
  response has `"synthetic": true`. Show that on the page. Real data keeps the same shape.
- **Facts are rules, not AI.** Each criterion's `status` (`pass`, `fail`, `unknown`) and its
  evidence come from stored data. `unknown` means there is no data to decide; it is never a
  guess. `verdict` is `ready` when every criterion passes, `not_ready` when any fails,
  otherwise `unknown`.
- **Criteria** are configured per team: `code_merged` (merged or excepted), `no_critical_flags`,
  `ci_green`, `risks_owned` (no open confirmed RAID risk without an owner; suggested items do
  not count), `docs_merged`.
- **A person decides.** `POST /readiness/{release}/decision` needs sign-in, the approver
  allowlist and a note. Decisions are appended, never edited; `decided_by` is a role.
- **`validated: false`** until the readiness backtest passes (ADR-0032); show "not validated".
- **`summary`** is `null` or AI sentences from verified facts only, each fact-checked.
- **Retro slips** are `dropped`, `moved` or `late_exception`. `first_warning_at` comes from
  forecast snapshots replayed as of each day (never today's data); `null` means the platform
  gave no warning before the slip. `lead_time_days` = `slipped_at` − `first_warning_at`.
- **Said vs showed** puts the RAID items from each meeting (suggested ones included, with
  their review state) next to the snapshot facts of the same date.
- **Patterns** are per pool (e.g. a SIG), never per person, and only for groups of at least
  `min_group` (10); smaller groups are counted in `suppressed_groups`.
- Times are UTC (ISO 8601).

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/readiness?release=` | | Criteria with evidence, verdict, decision log |
| POST | `/readiness/{release}/decision` | `{"decision": "go" \| "no_go" \| "defer", "note"}` (note 3+ characters) | The readiness, with the decision appended (201) |
| GET | `/retro` | | Slips with first warning dates and lead times |
| GET | `/retro/said-vs-showed` | | Meeting items next to same-day snapshot facts |
| GET | `/retro/patterns` | | Patterns per pool across releases |

Errors: 401 not signed in, 403 not an approver, 422 a missing note or a bad decision.
`?project=&release=` filters for the retro endpoints arrive with real data (#182, #183).

## Examples

`GET /readiness` after one decision:

### GET /readiness

```json
{
  "project": "kubernetes",
  "release": "v1.38",
  "as_of": "2026-11-25T21:00:00Z",
  "synthetic": true,
  "verdict": "not_ready",
  "criteria": [
    {
      "id": "code_merged",
      "name": "Code merged or excepted",
      "status": "fail",
      "detail": "Synthetic fixture: 2 features have a main PR that is not merged and has no exception.",
      "count": 2,
      "evidence": [{"text": "Synthetic fixture: Main PR #144232 is open.", "ref": "feature:kubernetes/enhancements#5419", "url": null}]
    },
    {
      "id": "no_critical_flags",
      "name": "No open critical flags",
      "status": "fail",
      "detail": "Synthetic fixture: 3 critical flags are open.",
      "count": 3,
      "evidence": [{"text": "Synthetic fixture: Main PR not merged by Code Freeze.", "ref": "feature:kubernetes/enhancements#5419", "url": null}]
    },
    {
      "id": "ci_green",
      "name": "CI green",
      "status": "pass",
      "detail": "Synthetic fixture: No failing check on the latest commits.",
      "count": 0,
      "evidence": []
    },
    {
      "id": "risks_owned",
      "name": "Every open risk has an owner",
      "status": "unknown",
      "detail": "Synthetic fixture: No confirmed RAID risks yet; suggested items do not count.",
      "count": null,
      "evidence": []
    },
    {
      "id": "docs_merged",
      "name": "Docs merged",
      "status": "pass",
      "detail": "Synthetic fixture: Every feature's docs PR is merged.",
      "count": 0,
      "evidence": []
    }
  ],
  "decisions": [
    {
      "decision": "no_go",
      "note": "Two main PRs are open without an exception.",
      "decided_by": "approver",
      "decided_at": "2026-11-25T21:00:00Z",
      "facts_as_of": "2026-11-25T21:00:00Z"
    }
  ],
  "summary": null,
  "validated": false,
  "validation_note": "Not validated: the readiness backtest has not run (ADR-0032)."
}
```

### GET /retro

```json
{
  "project": "kubernetes",
  "release": "v1.37",
  "label": "Synthetic retro (fixture)",
  "as_of": "2026-11-25T21:00:00Z",
  "synthetic": true,
  "sources": [
    {
      "kind": "snapshots",
      "title": "Synthetic forecast snapshots",
      "url": null,
      "synthetic": true
    }
  ],
  "totals": {
    "slips": 2,
    "warned": 1,
    "average_lead_time_days": 12.0,
    "median_lead_time_days": 12.0
  },
  "slips": [
    {
      "feature_key": "kubernetes/enhancements#9001",
      "title": "Synthetic fixture: dropped feature",
      "pool": "sig/node",
      "slip": "dropped",
      "slipped_at": "2026-11-17T12:00:00Z",
      "first_warning_at": "2026-11-05T12:00:00Z",
      "first_warning_flag": "late_main_pr",
      "lead_time_days": 12.0
    },
    {
      "feature_key": "kubernetes/enhancements#9002",
      "title": "Synthetic fixture: late exception",
      "pool": "sig/storage",
      "slip": "late_exception",
      "slipped_at": "2026-11-20T12:00:00Z",
      "first_warning_at": null,
      "first_warning_flag": null,
      "lead_time_days": null
    }
  ]
}
```

### GET /retro/said-vs-showed

```json
{
  "project": "kubernetes",
  "release": "v1.37",
  "synthetic": true,
  "rows": [
    {
      "date": "2026-11-10T12:00:00Z",
      "said": [{"item_id": 4, "raid_id": null, "type": "risk", "title": "Synthetic fixture: CI flakes on the node e2e job", "review": "suggested"}],
      "showed": [{"name": "features_at_risk", "value": 11}, {"name": "critical_flags", "value": 3}]
    }
  ]
}
```

### GET /retro/patterns

```json
{
  "project": "kubernetes",
  "synthetic": true,
  "min_group": 10,
  "suppressed_groups": 4,
  "patterns": [
    {
      "pool": "sig/node",
      "pattern": "late_main_pr",
      "text": "Synthetic fixture: main PRs opened in the last 14 days before Code Freeze",
      "value": 0.4,
      "n": 25,
      "releases": ["v1.36", "v1.37"]
    }
  ]
}
```

