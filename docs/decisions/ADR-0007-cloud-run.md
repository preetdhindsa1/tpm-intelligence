# ADR-0007: Run every workload on Cloud Run (plan only in phase 1)

- **Status:** accepted
- **Date:** 2026-11-21

## Context

CLAUDE.md §3 targets Google Cloud: Pub/Sub, Cloud SQL, Memorystore, Secret Manager, Cloud
Scheduler. Phase 1 ships Terraform as `validate` + `plan` only, with no apply. The
workloads have different shapes:
- the API serves HTTP and long-lived SSE streams;
- the web app is Next.js;
- the worker is a Pub/Sub pull loop with no HTTP port;
- the poller and migrations run to completion.

## Decision

`infra/` (flat root module, one file per concern):

- **API and web:** Cloud Run services. The API keeps `min_instance_count = 1` and
  `cpu_idle = false`, so its in-process forecast cache stays warm and SSE pushes run outside
  requests.
- **Worker:** a Cloud Run **worker pool** (`google_cloud_run_v2_worker_pool`) with one
  instance. It needs no HTTP port and no code change.
- **Poller:** a Cloud Run job, started every 5 minutes by Cloud Scheduler. That keeps data
  freshness under the 10-minute SLO.
- **Migrations:** a Cloud Run job, run before each deploy.
- **Pub/Sub:** `normalized-events`, the `worker` subscription and the dead-letter topic
  (5 attempts). The names match `pipeline/queue.py` and `pipeline/worker.py`.
- **Data:**
  - Cloud SQL Postgres 16 through the Cloud SQL connector socket (no authorized networks).
  - Memorystore Redis (auth on) through direct VPC egress.
- **Secrets:** in Secret Manager (`database-url`, `redis-url`, `github-token`).
  - Each workload has its own service account with least-privilege roles.
  - The GitHub token is added by hand.
- **Observability:**
  - Each Python workload runs the OTel Collector as a sidecar on `localhost:4317`.
  - The sidecar exports to Cloud Trace, Managed Prometheus and Cloud Logging
    (`observability/otel-collector-cloud.yaml`).
  - Alert policies cover queue backlog, dead letters and poller failures.
- **Checks:** CI and `make tf-plan` run fmt, validate and an **offline plan** (placeholder
  project, dummy token, `-refresh=false`). Measured 2026-11-21: 81 resources to add.

## Alternatives considered

- **GKE.** Full control, but a cluster to run and pay for at idle. Too heavy for this scale.
- **Worker as a Cloud Run service with Pub/Sub push.** Needs an HTTP handler and changes
  the queue code that ADR-0001 shares with Redis Streams.
- **Cloud Functions.** Poor fit for SSE and for the API's warm cache.
- **Private IP for Cloud SQL.** Needs private services access (peering). The connector is
  IAM-checked and simpler.

## Trade-offs and consequences

- **State is sensitive.** Terraform writes generated secrets (DB password, Redis auth) into
  state, so state belongs in a locked-down GCS bucket (backend block left commented).
- **API and web URLs depend on each other.** The API's CORS origin is the web URL, which
  only exists after the first apply, so it is a variable (`cors_origins`).
- **The browser's SSE URL is fixed at web image build time** (`NEXT_PUBLIC_API_URL`).
- **Zonal Cloud SQL** is cheaper. It needs REGIONAL to meet the 99.5% availability SLO.
- **The offline plan proves the configuration is consistent, not that apply succeeds.**
  Quotas, org policies and API enablement timing are untested until a real apply.
- **The poller alert approximates "2 failed polls in a row"** as 2 failures within 15
  minutes. The exact count lives in `sync_cursors.consecutive_failures`.

## AI vs rules

No AI involved.
