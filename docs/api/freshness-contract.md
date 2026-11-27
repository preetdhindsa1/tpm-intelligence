# Freshness contract (ADR-0036, #259)

Owner: claude-agent (API). Reader: cursor-agent (web). Pages never wait on GitHub or Jira,
so when a source is slow or down the data simply stops updating. This endpoint says how
old a release's data is, so the UI can say so.

## `GET /releases/{name}/freshness`

`name` is a bare release name (`v1.38`, `4.5.0`) or a key (`kubernetes:v1.38`). The
endpoint is cheap: it reads collector sync records and never computes a forecast.
Responses are scoped per tenant like every route (`X-TPM-Tenant`, ADR-0034).

```json
{
  "release": "kubernetes:v1.38",
  "status": "stale",
  "as_of": "2026-11-21T02:30:00Z",
  "checked_at": "2026-11-21T03:00:00Z",
  "sources": [
    {"kind": "planning", "system": "github", "last_success_at": "2026-11-21T02:58:00Z",
     "age_minutes": 2.0, "consecutive_failures": 0, "stale": false, "stale_after_minutes": 10},
    {"kind": "code", "system": "github", "last_success_at": "2026-11-21T02:30:00Z",
     "age_minutes": 30.0, "consecutive_failures": 3, "stale": true, "stale_after_minutes": 10}
  ]
}
```

| Field | Meaning |
|---|---|
| `status` | `fresh`: every source is within its threshold. `stale`: at least one is past it. `final`: the release shipped more than 3 days ago, so old data is expected. `unknown`: no sync records (fixture data, or a stack that was never polled). |
| `as_of` | The stalest source's last successful sync. `null` when `status` is `unknown` or a source never succeeded. |
| `checked_at` | When the API evaluated this. |
| `sources[].kind` | `planning` (enhancement issues, Jira) or `code` (pull requests). |
| `sources[].system` | `github` or `jira`. |
| `sources[].stale_after_minutes` | The threshold: 10 for GitHub (the freshness SLO), 70 for Jira (hourly sync). |
| `sources[].consecutive_failures` | Failed polls in a row. Error text is never returned. |

Errors: `404` for a release that doesn't exist for this tenant.

## What the UI shows (suggested, cursor-agent decides the layout)

- **`fresh`**: nothing, or a quiet "Updated N min ago".
- **`stale`**: a warning, "Data as of <as_of in the viewer's time zone>; <system> has not
  synced since then". Do not present odds or counts as live.
- **`final`**: "Final data (release shipped)".
- **`unknown`**: "Freshness not known" and never "live".
