# ADR-0002: Postgres as source of truth, Redis for cache, live push and the local queue

- **Status:** accepted
- **Date:** 2026-11-21

## Context

The platform joins planning data (work items, releases) with code data (PRs, reviews, CI)
and must:

- keep full **history** so backtests use only data dated before the prediction point (§6);
- model **many-to-many** work item ↔ release (KAFKA-21181 has fix versions 4.0.0–4.3.0);
- store links with **method, confidence and status**, where AI-suggested links can never
  count as fact without a verifier (§2.2);
- run complex relational queries (release → features → PRs → reviews) for the API and engine;
- push live updates to the dashboard (SSE) and cache hot reads.

## Decision

**Postgres** (Cloud SQL in the cloud) is the single source of truth, with SQLAlchemy 2.x
models in `pipeline/store/models.py` and Alembic migrations in `pipeline/store/migrations/`.

Schema shape:

| Table | Role |
|---|---|
| `events` | Append-only log of every normalized event. Unique `event_id` makes ingestion idempotent. An `UPDATE`/`DELETE`/`TRUNCATE` trigger rejects changes. Indexed on `(subject_kind, subject_key, occurred_at)` for as-of reads. |
| `work_items` | Generic planning item (`type`, self-referencing `parent_id`, `source`, `external_key`). |
| `releases` | Release plus key dates (enhancements freeze, code freeze, release). |
| `work_item_releases` | Many-to-many with `status` `active`/`removed`. Removed rows stay for history but are excluded from current-state queries. |
| `work_item_relations` | Item → item dependencies (KAFKA-19831 → KAFKA-17789). |
| `pull_requests`, `reviews`, `check_runs` | Code side: text and timestamps only, never source code. |
| `review_rounds` | Derived: reviews grouped per reviewer within a window (ADR-0006). |
| `links` | PR → work item with `method`, `confidence` in [0, 1], `status`, `evidence` (JSONB), `verified_by`. |
| `snapshots` | Computed state as of a time (e.g. a forecast on a given day). |
| `sync_cursors` | Incremental sync position plus `consecutive_failures` (feeds the "2 failed polls" alert). |

Rules are enforced **in the database**, not only in Python:

- CHECK constraints on every enumeration (text + CHECK rather than Postgres ENUM, so adding a
  value is a simple migration);
- `ai_suggested` links can be `verified` only when `verified_by` is set;
- `merged` PRs must have `merged_at`; `removed` memberships must have `removed_at`;
- no self-parenting, no self-relations;
- `timestamptz` everywhere.

**Redis** (Memorystore in the cloud) holds anything that can be lost and rebuilt from
Postgres: the response cache, the SSE fan-out channel, and the local event queue (ADR-0001).

## Alternatives considered

- **Event store only (rebuild everything from events on read).** Clean history, but every
  dashboard query would need projection code. We keep the events log *and* projections.
- **Postgres temporal tables / bi-temporal columns on every table.** Strong as-of support,
  but heavy for phase 1. The append-only events table plus `snapshots` gives as-of reads
  where we need them (forecast, backtest).
- **Graph database (Neo4j) for links and dependencies.** The graphs here are small (hundreds
  of features), and NetworkX in the engine handles critical paths in memory. Not worth a
  second database.
- **BigQuery.** Good for analytics, wrong for transactional upserts and low-latency API reads.
  May be added later as an export target.
- **Postgres LISTEN/NOTIFY instead of Redis for live push.** Workable, but payloads are
  limited to 8 kB, and Cloud Run scaling plus connection limits make Redis pub/sub simpler.

## Trade-offs and consequences

- Two stores to operate. Redis is non-authoritative, so losing it costs latency, not data.
- Current-state tables can drift from the events log if a projection has a bug. Mitigation:
  projections are idempotent and can be rebuilt from `events` (rebuild script lands with M7).
- The append-only trigger also blocks legitimate clean-up (e.g. GDPR-style deletion). Doing
  that would need an explicit migration that drops the trigger. That is deliberate friction.
- `compare_metadata` runs in the test suite, so a model change without a migration fails CI.

## AI vs rules

No AI involved. The `links` CHECK constraint is the database-level guard that AI-suggested
links cannot become facts on their own.

## Addendum (2026-11-22, M7 step 1): release views are served stale while they recompute

**Problem.** The API keeps one computed view per release (projection of about 294k events,
assessment, Monte Carlo, recalibration). It used to recompute **in the request** whenever
new events arrived or the 5-minute TTL passed, so whoever came next waited for it.

**Decision: stale-while-revalidate.**
- Once a release has a view, requests get it at once. A single background thread
  recomputes, and the next request gets the new view.
- Pages show "data as of", so a stale view is labelled by its own time.
- A person's own action (`invalidate`, e.g. confirming a link) still waits, so they see
  its effect straight away.
- The live-update stream waits for the new view before telling the browser to reload, so
  a reload always shows the new data.
- On boot, the API computes the current release in the background. A warmer thread then
  refreshes viewed releases every 30 s when they are stale, even if nobody is looking.

**Alternatives.**
- Make the recompute incremental (re-project only new events): the larger, right fix
  eventually, but the engine projects the world as a pure function of all events.
- Shorter TTL: makes it worse.
- A precomputed views table in Postgres: needs a writer service; not needed yet on one API
  instance.

**Trade-off.** For up to one recompute time (measured 23 s idle, about 40 s under load),
a page may show data that is a few minutes old. Its "as of" time says so.

**Measured** (2026-11-22, `docs/results/api-latency-swr-20261122.json`). v1.38 summary,
feature table and dependencies were requested every 5 s for 11 minutes, which crosses two
cache expiries. Local Docker on a laptop.

| | Requests | Over 2 s | Slowest | p95 (summary / features / dependencies) |
|---|---|---|---|---|
| Before | 357 | 2 (one per cache expiry) | 23.1 s | 0.09 / 0.02 / 0.16 s |
| After | 366 | 1 (cold start: first request after the redeploy, during boot warm-up) | 29.6 s | 0.08 / 0.04 / 0.21 s |

After the change, the cache expiry was recomputed in the background (24.5 s) with no slow
request. The remaining slow request was the cold start, which the boot warm-up shortens
but cannot remove. p95 hides the problem in both runs: the waits were rare but long, so
"requests over 2 s" is the number that matters.
