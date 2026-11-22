# TPM Intelligence Platform

Predicts which features in a large multi-team software release will slip, explains why, and
drafts the executive update for a human to approve.

- **The plan** comes from planning tickets (Kubernetes enhancement issues; later, Jira).
- **The truth** comes from the code (PRs, reviews, CI, merges).
- The platform links them, computes facts and odds with deterministic code and statistics,
  and (in later phases) uses AI only to explain, with every AI claim checked against the data first.

> **Status: phase 1, dashboard.** Collect → link → engine → API → web dashboard runs end to end on local
> Docker. **Kubernetes is a live example team** (see `connectors/teams/`); the platform is meant for any
> cross-functional release. The forecast is built and backtested. After recalibration it beats the
> historical base rate in 9 of 12 backtest cases but not all (see results), so the dashboard labels
> forecast odds "not validated".
> Everything else below is **TBD (not yet measured)**.

### Plug in another team

Copy `connectors/teams/_template.yaml`, point at planning + code repos + a release calendar, pick a
`link_pack` (`kep` or `jira_key`), then `make backfill TEAM=<id> RELEASE=<name>`. Details:
[`connectors/teams/README.md`](connectors/teams/README.md) and ADR-0003.

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
make backfill TEAM=kubernetes RELEASE=v1.38   # full window, ignores cursors
make poll TEAM=kubernetes RELEASE=v1.38       # incremental from the stored cursors
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
and ADR-0007):

```bash
make tf-validate            # fmt + validate, in Docker
make tf-plan                # offline plan: placeholder project, dummy token
```

`make help` lists all targets.

## Measured results

| Metric | Value |
|---|---|
| Forecast backtest, v1.35-v1.38 at 28/14/7 days before freeze, recalibrated | **Beats the base rate in 9 of 12 cases, not all**: skill −0.29 to +0.25 (v1.36 fails at 14 and 7 days, v1.37 at 7 days); improves on raw odds everywhere; AUC 0.51-0.76. Odds stay "not validated". Measured 2026-11-22; details in ADR-0005 |
| Linking coverage: tracked v1.38 features with ≥1 verified PR | **68 / 69 (98.6%)**, measured 2026-11-21 21:36 UTC |
| PRs in the v1.38 window with a verified link | **609 / 2,757 (22.1%)**; 24 suggested-only; 2,124 unlinked (count as load) |
| Linking precision per method | TBD (not yet labelled): 70-row stratified v1.38 sample ready in `evals/cases/linking.csv` |
| Fact checker vs labelled claims (`make evals`) | **43 / 43 agree** (22 verified, 21 removed across all 5 reasons). Labels are proposed by the developer, pending TPM review. Measured 2026-11-22 |
| First real AI calls (`make ai-smoke`, Haiku 5.5, #6395 fact sheet) | `smoke.v1`: 9 verified / 10 removed, mostly a checker false positive on bare feature numbers ("feature 6395"), now fixed. `smoke.v2`: **16 verified / 1 removed** (a sentence stating uncited numbers). About **$0.001 per call**; repeat call served from cache at $0. Single runs, measured 2026-11-22; not an accuracy benchmark |
| Risk analyst live evals (12 real v1.37/v1.38 cases, Haiku 5.5, `risk_analyst.v4`) | **Removal rate 4.0%**, critical-flag coverage 100%, odds honesty 100%, 3–5 claims per note, $0.024 per run. Earlier prompts: v1 and v3 failed the gate; v2 passed it but was rejected after the notes were read (wrong wording). Measured 2026-11-22; small sample |
| VP summarizer live evals (4 real v1.37/v1.38 release fact sheets, Opus 5.5, `vp_summary.v1`) | **0% removed**, at most 217 words, top-3 at-risk coverage 100%, asks grounded 100%, odds honesty 100%; $0.54 per run (about $0.14 per draft). Measured 2026-11-22; small sample |
| Link suggester: shortlist recall (rule-linked PRs with keys hidden, no AI) | Right feature in the 12-item shortlist **88.1%** (v1.37, 1,040 PRs) and **86.8%** (v1.38, 949 PRs). Measured 2026-11-22; ADR-0011 |
| Link suggester live eval (60 hidden-key cases, Haiku 5.5, `link_suggester.v1`) | **Precision 84.8%**, recall 70%, false links on negatives 20%, 5.7% dropped by checks, $0.025 per run. Measured 2026-11-22; small sample |
| Link suggester on real v1.38 unlinked PRs | 1,797 unlinked → **104 suggestions** waiting for review, 1,636 "none", 11 dropped, 46 with no shortlist; **$0.54** in total. Reviewed precision: TBD (not yet reviewed). None of these count until a person confirms them |
| Engine: assess all 106 v1.38 features from 60,230 events | project 0.22 s + assess 0.89 s (single run, laptop, Docker; not a p95) |
| API `/releases` (dashboard home), 162k events, 6 releases | cold cache **6.9 s**, warm 0.06 s (was several minutes cold: it forecast every release). Single runs, laptop, Docker; measured 2026-11-21, not a p95 |
| API v1.38 feature table, cold cache, 3 concurrent requests | **~21 s** each, sharing **one** computation (was one computation per request). Single run, measured 2026-11-21 |
| Data freshness | TBD (not yet measured) |
| Event → dashboard latency (p95) | TBD (not yet measured) |

Coverage counts *whether* a link exists, not whether it is right. Reproduce with
`DATABASE_URL=... uv run python scripts/measure_linking.py --release v1.38`.

## Phase 2 progress

- **M1 done: fact checker and evals** (`verify/`, `evals/`, ADR-0008). Engine output becomes
  a typed fact sheet. AI claims must cite fact keys and are verified or removed with a
  reason. No AI agents yet.
- **M2 done: AI plumbing** (`agents/`, ADR-0009). One gateway to Claude with models from
  config, structured output, a $2/day budget (slow at 80%, pause at 100%), a cache keyed by
  a hash of the input facts, versioned prompts, OTel spans and metrics, and self-hosted
  Langfuse for AI traces (`make langfuse-up` → http://localhost:3001). `make ai-smoke` makes
  one real, fact-checked call.
- **M3a done: risk analyst** (ADR-0010). The feature page has a "Why this feature is at risk"
  panel: 2–5 AI-written claims, each verified against the data, generated when the page
  is opened and reused until facts change. LangGraph loop: draft → fact-check → one
  redraft if more than 30% of claims are removed. `make evals-live` runs paid agent evals;
  CI requires a passing run for the current prompt and model.
- **M3b done: VP summarizer and TPM approval** (ADR-0010). "Executive update →" on the
  release page. Opus drafts about 200 words in Summary / At risk / Removed / Asks, using
  only verified claims; asks come from fixed rules. The TPM edits (edits are re-checked),
  then approves or rejects, recorded as "Harpreet (local, unauthenticated)". Nothing is
  ever sent: approved updates offer "Copy as Markdown".

- **M4 done: AI link suggester and review queue** (ADR-0011). Code shortlists 12 features
  for each unlinked PR. Haiku picks one or says none, quoting both sides, and the quotes
  are checked word for word. "Link review →" on the release page lists suggestions; only a
  person's confirmation makes a link count. `make suggest-links RELEASE=v1.38` runs it
  within the daily budget.

## Limitations

- Phase 1 runs locally only. The Terraform in `infra/` is checked with an offline plan
  (84 resources) but has never been applied, so a real deployment is untested.
- Phase 2 so far: fact checker, AI gateway, risk analyst, VP summarizer with TPM approval, and the AI link suggester with a review queue. Still to come: simulator, dashboard redesign, forecast improvements. Sign-in, webhooks, Jira and cloud deploy are Phase 3.
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
