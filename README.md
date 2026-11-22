# TPM Intelligence Platform

Predicts which features in a large multi-team software release will slip, explains why, and
drafts the executive update for a human to approve.

- **The plan** comes from planning tickets (Kubernetes enhancement issues; later, Jira).
- **The truth** comes from the code (PRs, reviews, CI, merges).
- The platform links them, computes facts and odds with deterministic code and statistics,
  and (in later phases) uses AI only to explain, with every AI claim checked against the data first.

> **Status: phase 1, dashboard.** Collect → link → engine → API → web dashboard runs end to end on local
> Docker. The forecast is built and backtested, and it **does not yet beat the historical base rate** (see
> results), so the dashboard labels forecast odds "not validated".
> Everything else below is **TBD (not yet measured)**.

## Architecture

```
Sources     Kubernetes GitHub (polled)
              │
Collect     github_poller ──► normalized events
              │
Queue       Redis Streams (local) / Pub/Sub (cloud)  — trace context in message attributes
              │
Facts       linker → dependency graph + critical path → rule flags → Monte Carlo forecast
              │
Store       Postgres (source of truth) + Redis (cache, live push)
              │
Serve       FastAPI (+ SSE) ──► Next.js dashboard
Operate     OpenTelemetry → Collector → Jaeger (local) / Cloud Trace (cloud)
```

## Run locally

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), Python 3.12.

```bash
cp .env.example .env        # add a read-only GITHUB_TOKEN
make install                # Python deps into .venv
make test                   # ruff + mypy + pytest
make up                     # Postgres (+ migrations), Redis, OTel Collector, Jaeger, API, worker, web
curl localhost:8000/healthz
open http://localhost:3000  # dashboard: releases → feature health table → feature detail
open http://localhost:16686 # Jaeger: traces from tpm-api and tpm-worker
```

API (all numbers computed by `engine/`; odds are labelled `validated: false` until a
backtest beats the base rate):

```bash
curl localhost:8000/releases
curl localhost:8000/releases/v1.38/features          # health table: odds, flags, linked PRs
curl localhost:8000/releases/v1.38/features/6395     # timeline, critical path, PRs, assumptions
curl localhost:8000/releases/v1.38/load              # open unlinked PRs per SIG (not per person)
curl -N localhost:8000/releases/v1.38/stream         # Server-Sent Events: "update" on new data
```

Check one trace end to end: keep the stream open, publish the real #6395 Code Freeze event,
and open the printed trace ID in Jaeger. It spans `tpm-sample-publisher` → queue →
`tpm-worker` (Postgres insert) → `tpm-api` (`api.push_update` → recompute → SSE send).

```bash
docker compose exec api python -m pipeline.sample
```

Integration tests need the stack running. Postgres tests create and drop a throwaway
database on the server at `DATABASE_URL`. The Pub/Sub test also needs the
emulator:

```bash
docker run -d --rm -p 8085:8085 gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators \
  gcloud beta emulators pubsub start --host-port=0.0.0.0:8085 --project=tpm-local
DATABASE_URL=postgresql+psycopg://tpm:tpm@localhost:5432/tpm \
REDIS_URL=redis://localhost:6379/15 PUBSUB_EMULATOR_HOST=localhost:8085 make test-integration
```

Load real Kubernetes data (needs `GITHUB_TOKEN` in `.env`). Events flow poller → queue →
worker → Postgres `events`. Projections into features, PRs and links arrive in M7.

```bash
make backfill RELEASE=v1.38   # full window, ignores cursors
make poll RELEASE=v1.38       # incremental from the stored cursors
```

Dashboard (Next.js, `web/`): the release page shows the feature health table (odds with
range, flags, linked PRs, SIGs). Unlinked-PR load per SIG is API-only for now. A feature page shows its timeline
(tracked, removed, re-added), critical path, PRs and the assumptions behind the odds. Pages
refresh live over SSE when new data lands. The server renders with `API_URL` (in-network);
the browser opens the SSE stream at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

```bash
make web-test               # eslint + tsc + vitest + next build, in Node 20 via Docker
```

Cloud infrastructure (Terraform, **plan only, never applied**; see [`infra/README.md`](infra/README.md)
and ADR-0003):

```bash
make tf-validate            # fmt + validate, in Docker
make tf-plan                # offline plan: placeholder project, dummy token
```

`make help` lists all targets.

## Measured results

| Metric | Value |
|---|---|
| Forecast backtest, v1.37 and v1.38 at 28/14/7 days before freeze | **Does not beat the base rate yet**: Brier 0.31-0.37 vs baseline 0.18-0.21 (skill −0.6 to −0.9); ranking AUC 0.60-0.68. Measured 2026-11-21; details and diagnosis in ADR-0005 |
| Linking coverage: tracked v1.38 features with ≥1 verified PR | **68 / 69 (98.6%)**, measured 2026-11-21 21:36 UTC |
| PRs in the v1.38 window with a verified link | **609 / 2,757 (22.1%)**; 24 suggested-only; 2,124 unlinked (count as load) |
| Linking precision per method | TBD (not yet measured): needs a hand-labelled sample |
| Engine: assess all 106 v1.38 features from 60,230 events | project 0.22 s + assess 0.89 s (single run, laptop, Docker; not a p95) |
| API `/releases` (dashboard home), 162k events, 6 releases | cold cache **6.9 s**, warm 0.06 s (was several minutes cold: it forecast every release). Single runs, laptop, Docker; measured 2026-11-21, not a p95 |
| API v1.38 feature table, cold cache, 3 concurrent requests | **~21 s** each, sharing **one** computation (was one computation per request). Single run, measured 2026-11-21 |
| Data freshness | TBD (not yet measured) |
| Event → dashboard latency (p95) | TBD (not yet measured) |

Coverage counts *whether* a link exists, not whether it is right. Reproduce with
`DATABASE_URL=... uv run python scripts/measure_linking.py --release v1.38`.

## Limitations

- Phase 1 runs locally only. The Terraform in `infra/` is checked with an offline plan
  (81 resources) but has never been applied, so a real deployment is untested.
- No AI agents, simulator, sign-in, webhooks or Jira in phase 1.
- **PR discovery.** Kubernetes enhancement issues have no timeline cross-reference events
  for their PRs (checked on #6395, 2026-11-21). PRs are found from the PR list in the issue
  description (the release team's tracking list) and from KEP references in PR text.
- **Issue history comes from GraphQL.** GitHub's REST issue events and timeline endpoints
  stop at about 300 items and drop the *newest* events on long-lived KEPs. In the first v1.38
  backfill, 9 of 70 current issues were missing their v1.38 history. One of them, #2570, was
  removed at Code Freeze and re-added. History now comes from GraphQL `timelineItems`.
- **Release-team project board not read.** Its status field needs a token with
  `read:project`. Milestone and label history rebuild the tracking timeline without it.
- **Backfill window.** Past releases include PRs *created or merged* between cycle start and
  release, plus every PR in a tracking list. A long-running PR that was opened earlier and
  not merged in the window is missed unless a tracking list names it.
- **Other repos.** Tracked PRs outside kubernetes/kubernetes (e.g. k/website docs) are
  counted but not fetched in phase 1.
- **`kep.yaml` is read as it is today**, not as it was at a past prediction point. Backtests
  must not use spec fields that changed late (e.g. stage).
- **Engine text fields are today's text.** Labels, release membership, PR state, reviews and
  CI are rebuilt strictly as of the prediction point. Issue descriptions, PR bodies and
  `kep.yaml` are not versioned by GitHub, so the latest text is used (ADR-0005).
- **API recompute is not incremental.** Each change to the data re-projects every stored event
  (about 9 s for 138k events on a laptop). The first request also fits the recalibration
  (about 15 s). Fine for polled data within the 30 s target, but not for heavy webhook traffic.
- **CI flags cannot tell required checks from optional ones.** Prow does not mark them in the
  API data we read, so `ci_failing` counts any failing check on the latest commit.
- Release dates come from a checked-in calendar
  (`collectors/github_poller/release_calendar.yaml`) with a source link per release. The
  v1.36 and v1.37 release days have no time of day in the source, so they are stored as 00:00 UTC.

## Design decisions

See [`docs/decisions/`](docs/decisions/).

## Data

Public Kubernetes data only. The platform measures flow and bottlenecks, not individual performance.
