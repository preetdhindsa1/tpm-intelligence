# RAID tracker API contract (v1)

Wave 4 (docs/plan/e2e-plan.md), ADR-0030. Written before the RAID page is built, so the
web app (cursor-agent) and the API (claude-agent) can be built in parallel. Every example
below is produced by the API's synthetic fixture and checked by `tests/api/test_raid.py`.

## Rules the page can rely on

- **Synthetic until the store lands.** Until #180, every response has `"synthetic": true` and
  every source is labelled synthetic. Show that on the page. Real items arrive with
  `"synthetic": false` and the same shape.
- **AI never confirms.** The extractor creates items with `review: "suggested"`. Only a person
  (signed in, on the approver allowlist, ADR-0016) confirms, edits or rejects.
- **RAID ID** `{WORKSTREAM}-{TYPE}-{SEQ}` (types R risk, A action, I issue, D decision,
  Q question), e.g. `K8S-R-001`. Given on the first confirm or edit; never changed, never
  reused, never given to a rejected item. Suggested items have `raid_id: null`; use
  `item_id` in URLs.
- **Quote** is the source's words, verbatim. It cannot be edited.
- **Owner** is a role or team (`"SIG Storage"`, `"Release lead"`), never a person's name.
- **Lifecycle** `status`: open → in_progress → closed / superseded. **Review** `review`:
  suggested → confirmed / edited / rejected.
- **Merge** is only ever suggested (`merge_suggestion` with a reason); nothing is merged
  without a person.
- **History** is append-only; `actor` is a role (`extractor`, `approver`), never a login.
- Times are UTC (ISO 8601).

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/raid` | | Confirmed and edited items (the tracker) |
| GET | `/raid/queue` | | Suggested items waiting for review |
| GET | `/raid/summary` | | Counts by type and state, risks without an owner, waiting count |
| GET | `/raid/{item_id}/history` | | Every change, oldest first |
| POST | `/raid/{item_id}/confirm` | `{"note"?}` | The item, now `confirmed`, with its RAID ID |
| POST | `/raid/{item_id}/edit` | `{"title"?, "type"?, "owner"?, "status"?, "note"?}` | The item, now `edited` (and confirmed) |
| POST | `/raid/{item_id}/reject` | `{"reason"}` (required, 3+ characters) | The item, now `rejected`, no RAID ID |

Errors: 401 not signed in, 403 not an approver, 404 unknown item, 409 the item was already
rejected, 422 a missing reason or a bad field.

**Scope.** `GET /raid`, `/raid/queue` and `/raid/summary` take `?project=&release=`
(default `kubernetes`, `v1.38`). With a database configured, the API serves the RAID store:
real items extracted from public meeting notes, `"synthetic": false`, each source linking
to its Google Doc with the meeting date in the title. Quotes have people's names masked as
`[participant]` (ADR-0030 addendum 3). Without a database (tests, local runs without
Postgres) the API serves the synthetic fixture below, `"synthetic": true`.

## Examples

### GET /raid

```json
{
  "project": "kubernetes",
  "release": "v1.38",
  "as_of": "2026-11-25T21:00:00Z",
  "synthetic": true,
  "items": [
    {
      "item_id": 1,
      "raid_id": "K8S-R-001",
      "workstream": "K8S",
      "type": "risk",
      "title": "Main PR for enhancement #6395 may miss Code Freeze",
      "quote": "Synthetic: the main PR for #6395 still needs an approver from SIG Storage.",
      "source": {"kind": "meeting", "title": "Synthetic release-team meeting (fixture, not real notes)", "url": null, "date": "2026-11-10T17:00:00Z", "synthetic": true},
      "owner": "SIG Storage",
      "status": "open",
      "review": "confirmed",
      "links": [{"kind": "feature", "ref": "kubernetes/enhancements#6395", "method": "explicit_key", "status": "verified"}],
      "merge_suggestion": null,
      "created_at": "2026-11-10T17:00:00Z",
      "updated_at": "2026-11-10T17:00:00Z"
    }
  ]
}
```

### GET /raid/queue

```json
{
  "project": "kubernetes",
  "release": "v1.38",
  "as_of": "2026-11-25T21:00:00Z",
  "synthetic": true,
  "items": [
    {
      "item_id": 4,
      "raid_id": null,
      "workstream": "K8S",
      "type": "risk",
      "title": "CI flakes on the node e2e job",
      "quote": "Synthetic: node e2e has been flaky all week.",
      "source": {"kind": "meeting", "title": "Synthetic release-team meeting (fixture, not real notes)", "url": null, "date": "2026-11-10T17:00:00Z", "synthetic": true},
      "owner": null,
      "status": "open",
      "review": "suggested",
      "links": [],
      "merge_suggestion": null,
      "created_at": "2026-11-10T17:00:00Z",
      "updated_at": "2026-11-10T17:00:00Z"
    }
  ]
}
```

### GET /raid/summary

```json
{
  "project": "kubernetes",
  "release": "v1.38",
  "as_of": "2026-11-25T21:00:00Z",
  "synthetic": true,
  "by_type": [
    {
      "type": "risk",
      "suggested": 2,
      "open": 1,
      "in_progress": 0,
      "closed": 0,
      "superseded": 0,
      "rejected": 0
    },
    {
      "type": "action",
      "suggested": 0,
      "open": 0,
      "in_progress": 0,
      "closed": 1,
      "superseded": 0,
      "rejected": 0
    },
    {
      "type": "issue",
      "suggested": 0,
      "open": 0,
      "in_progress": 0,
      "closed": 0,
      "superseded": 0,
      "rejected": 0
    },
    {
      "type": "decision",
      "suggested": 0,
      "open": 1,
      "in_progress": 0,
      "closed": 0,
      "superseded": 0,
      "rejected": 0
    },
    {
      "type": "question",
      "suggested": 0,
      "open": 0,
      "in_progress": 0,
      "closed": 0,
      "superseded": 0,
      "rejected": 1
    }
  ],
  "risks_without_owner": 0,
  "waiting_for_review": 2
}
```

### GET /raid/{item_id}/history

```json
{
  "item_id": 1,
  "raid_id": "K8S-R-001",
  "synthetic": true,
  "history": [
    {
      "at": "2026-11-10T17:00:00Z",
      "actor": "extractor",
      "action": "suggested",
      "changes": {"type": "risk", "title": "Main PR for enhancement #6395 may miss Code Freeze"},
      "reason": null
    },
    {
      "at": "2026-11-10T17:00:00Z",
      "actor": "approver",
      "action": "confirmed",
      "changes": {"raid_id": "K8S-R-001"},
      "reason": null
    }
  ]
}
```

`POST /raid/4/confirm` with `{"note": "Owner to be assigned in the next meeting."}`:

### POST /raid/{item_id}/confirm

```json
{
  "item_id": 4,
  "raid_id": "K8S-R-002",
  "workstream": "K8S",
  "type": "risk",
  "title": "CI flakes on the node e2e job",
  "quote": "Synthetic: node e2e has been flaky all week.",
  "source": {
    "kind": "meeting",
    "title": "Synthetic release-team meeting (fixture, not real notes)",
    "url": null,
    "date": "2026-11-10T17:00:00Z",
    "synthetic": true
  },
  "owner": null,
  "status": "open",
  "review": "confirmed",
  "links": [],
  "merge_suggestion": null,
  "created_at": "2026-11-10T17:00:00Z",
  "updated_at": "2026-11-25T21:00:00Z"
}
```
