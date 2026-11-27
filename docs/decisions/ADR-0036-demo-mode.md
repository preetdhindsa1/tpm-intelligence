# ADR-0036: Demo mode: the stored data is the cache, and every release says how old it is

- **Status:** accepted for Wave 7 (#259). The owner approved the Wave 7 plan on
  2026-11-27 by merging #256 after it was posted.
- **Date:** 2026-11-27

## Context

The Wave 7 plan asks for "demo mode with a cached dataset, so the demo works if GitHub or
Jira is slow". Before designing a cache, I checked what a page actually depends on. The
evidence below is from the code as of `main` on 2026-11-27.

- **No API route calls a source system.** No module in `api/` uses an HTTP client, a
  GitHub client or a Jira client (`grep -rln "httpx|GitHubClient|JiraClient" api/` finds
  nothing). Every page is computed from Postgres: the stored events, then the in-memory
  release views (`api/service.py`, stale-while-revalidate).
- **Collectors run apart from the API.** In the cloud they are separate Cloud Run jobs
  started by Cloud Scheduler: GitHub every 5 minutes, Jira hourly at :17 (ADR-0017,
  `infra/variables.tf`).
- **A failed poll changes no stored data.** `GitHubPoller._guarded` and the Jira sync
  catch each stream's failure, keep its cursor and count it in
  `sync_cursors.consecutive_failures`. The other streams still run. That count feeds the
  "2 failed polls in a row" alert.
- **Retries happen in the collector.** The HTTP wrapper retries 5xx errors, 429 responses
  and timeouts with backoff, and gives up when a rate limit asks for too long a wait
  (`collectors/http.py`).

So a slow or failing GitHub or Jira already cannot slow down or break a page: the pages
keep showing the last data that was stored. What is missing is honesty. **Nothing tells a
reader that the data has stopped updating.** A demo showing three-day-old odds as if they
were live is worse than one that says it is three days old (CLAUDE.md principle 5).

## Decision

### 1. No second copy of the data

The demo tenant's rows in Postgres are the cached dataset. Adding a snapshot file or a
second store would create a second source of truth that can drift from the first, and it
would protect against nothing that is not already covered:

- GitHub or Jira being slow or down is covered by the design above.
- A Cloud SQL outage is covered by Cloud SQL's own availability and by the tested backup
  restore (`docs/results/restore-test-20261124.json`). A file-based fallback for a
  database outage would be a different product (a static demo), not this ADR.

### 2. Each release reports how fresh its data is

New endpoint: `GET /releases/{name}/freshness`. The contract is in
`docs/api/freshness-contract.md`.

- **Sources:** the `sync_cursors` rows for the release's own streams. A stream belongs to
  a release when two things hold:
  - its repository is in the team's config (planning repo or code repos), or its Jira key
    is the team's project key;
  - its release segment names this release. The Jira stream joins several releases with
    `+`.
- **Fields per source:** kind (planning or code), system (github or jira), last successful
  sync, age in minutes, failures in a row, and whether it is stale.
- **The error text is never returned.** `last_error` can hold URLs and request details.
  The API returns only counts and times.
- **When a source is stale:** its last success is older than its system's threshold:
  - GitHub: 10 minutes, the polled-data freshness SLO (CLAUDE.md section 9). On 2026-11-23
    the measured worst gap was 6.2 minutes between successful polls, plus 2.1 minutes of
    poll time (`docs/results/poll-freshness-cloud-20261123.json`).
  - Jira: 70 minutes. It syncs hourly, plus 10 minutes of slack. Apache rate limits
    (CLAUDE.md section 7) rule out polling Jira as often as GitHub.
- **`as_of`** is the oldest last success among the release's sources. A release is only
  as fresh as its stalest source.
- **`status`:**
  - `fresh`: every source is within its threshold.
  - `stale`: at least one source is past its threshold. The UI says "Data as of <time>"
    and does not present the numbers as live.
  - `final`: the release shipped more than 3 days ago, the same 3-day window the engine
    uses to judge outcomes. The pollers stop at release day, so old data is expected and
    is not a fault.
  - `unknown`: there are no sync records for the release, for example the fixture data
    or a local stack that was never polled. The UI says nothing is known about freshness,
    never "live".
- **Scope:** `sync_cursors` is under row-level security like every tenant table
  (ADR-0034), so each tenant sees only its own sources. The isolation test, which calls
  every GET route as two tenants, covers the new route automatically.

### 3. Webhooks do not count as "fresh"

Webhook events arrive between polls. Polls guarantee completeness, because a missed
webhook is repaired by the next poll, so freshness is measured from successful polls
only. A release that receives webhooks but whose poll keeps failing is stale. This
understates freshness, and that is the safe direction.

### 4. Every failure mode is tested

- In the collector, one test per failure: 5xx, a 429 that asks for too long a wait, and a
  timeout. Each must count a failure, keep the cursor and let the other streams finish.
- A pure function computes freshness from the stream rows. Its tests cover each status,
  the per-system thresholds, the Jira `+` streams, and streams from another team being
  ignored.
- The route has its own test.

## Alternatives considered

- **Serve a cached JSON snapshot when the source is slow.** Rejected: the API never waits
  on a source, so there is nothing for a snapshot to stand in for.
- **Mark a view stale when no new event has arrived for N minutes.** Rejected: a quiet
  release with no activity would look broken. A successful poll that found nothing new is
  still fresh.
- **Show one global "data as of" for the whole site.** Rejected: each team has its own
  sources and schedules, and Kafka's hourly Jira sync would make Kubernetes look stale.

## Trade-offs

- Freshness reflects when collection last succeeded, not when the page was computed. New
  events reach the dashboard within seconds (webhook to push p95 9.65 s,
  `docs/results/webhook-latency-cloud-20261124T044532Z.json`), so the two differ by about
  that much.
- The thresholds live in code (`api/freshness.py`), not in each team's config. If a
  tenant schedules its polls differently, its thresholds should move into `TeamConfig`
  then, with a new addendum here.
