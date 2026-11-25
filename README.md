# Program Intelligence Platform

_Formerly TPM Intelligence (renamed 2026-11-23, ADR-0021)._

**AI-native program management · every fact verified.** A program management platform that a
company plugs into its own tools. It runs the routine parts of program management continuously
(tracking, bottlenecks, risks, forecasts, stakeholder updates) so TPMs spend their time on
decisions. Now that agents write code at machine speed, it shows where delivery is really
stuck: review capacity, review depth and rework.

- **The plan** comes from planning tools (Kubernetes enhancement issues on GitHub, Apache Kafka on Jira).
- **The truth** comes from the work (PRs, reviews, CI, merges).
- The platform links them, computes facts and odds with deterministic code and statistics, and
  uses AI only to explain, with every AI claim checked against the data first. A person approves
  anything that leaves the platform.

### The screens (UX v1, locked 2026-11-24)

Spec: [`docs/ux/ux-v1-locked.md`](docs/ux/ux-v1-locked.md). Shell, color, and stage: ADR-0024.
JSON the screens read: [`docs/api/ux-v1-contract.md`](docs/api/ux-v1-contract.md).

The menu on every page is **Portfolio · Live Cockpit · Decision Studio · AI-native PDLC · Connect your tools**.
The current page is underlined. The front page also shows **Sign in** (only when GitHub or local login is
configured) and **Open the live demo**, which opens Live Cockpit for the last program viewed, or Portfolio
if there is none. Other screens show Search (⌘K: the five screens plus the open release's sections), a
Live indicator, and the signed-in avatar. The Live label does not claim freshness; each page shows its
own data-as-of time. Sentence case everywhere except Program Intelligence Platform, Live Cockpit,
Decision Studio, and Shadow-Org Simulator.

Live Cockpit and Decision Studio use the program in the URL, then the last program stored in the
browser, otherwise Portfolio. The header is a breadcrumb (`Portfolio / Kubernetes · v1.38`) plus stage,
Code Freeze, release date, and data as of. Live Cockpit sections are tabs: Overview, Dependencies,
Executive update, Link review. Feature pages sit under Overview. Decision Studio has no tabs.

| Screen | Route | What it shows | Data |
|---|---|---|---|
| Front page | `/` | Dark hero and live program cards; five stages (Plan · Build · Freeze · Launch · Learn) with module status; three stories drawn from live facts (Code Freeze removals, human reviews on this repo's merged PRs, Kafka features linked to code) — a story is omitted when its source is missing; Built for trust scorecard, failures included; a 2:00 demo outline (five chapters, no recording published) | `GET /portfolio`, release summaries, `GET /lab`, `web/lib/measured.ts` |
| Portfolio | `/portfolio` | "Here are the live programs." Stage, scope, biggest bottleneck, next decision; Waiting on you; Across programs; Coming next (RAID, readiness, retros, labeled Planned) | `GET /portfolio` (ADR-0025) |
| Live Cockpit | `/projects/{project}/releases/{name}` | One program: lifecycle bar, five stat tiles, the #6395 time machine (Kubernetes v1.38 only), Code Freeze chart or pre-freeze odds, a decide card, and the verified executive brief | Release endpoints |
| Decision Studio | `/projects/{project}/releases/{name}/simulate` | Pool and lever pickers, baseline vs scenario as ranges, powered by the Shadow-Org Simulator. Before a run the comparison says Illustrative and shows no numbers. The "not validated" banner uses the API's replay checks | `GET /releases/{name}/simulator` (ADR-0012) |
| AI-native PDLC | `/pdlc` | How this repository's pod (1 human, 2 AI agents, 1 bot) builds, checks and ships: seven stages, metrics vs targets, rules checked against real PRs. `/lab` is the per-release report; the same menu item stays underlined | `GET /lab` (ADR-0023) |
| Connect your tools | `/connect` | Three steps (connect, describe releases, first program). Connector status comes from live programs. Read-only, human approval, and public-demo privacy. It does not start a sign-up | `GET /portfolio` and connector configs |
| All releases | `/releases` | Every collected release, including past ones. Not in the main menu. Old `/releases/{name}` links redirect to `/projects/{project}/releases/{name}` | `GET /releases` |

A failed API call shows the error text and no stand-in numbers. Unvalidated models say "not validated".
Planned modules say Planned and show no invented counts. The screenshots further down are the
2026-11-22 dashboard (ADR-0013), before this menu.

> **Status: phase 3, live in Google Cloud.** Live demo:
> https://program-intelligence-platform-109199755245.us-central1.run.app (deployed 2026-11-23, ADR-0017; URL renamed
> 2026-11-23, ADR-0021).
> Collect → link → engine → API → web dashboard runs end to end, in the cloud and on local
> Docker. Example teams (see `connectors/teams/`): **Kubernetes** (GitHub, polled every 5 minutes),
> **Apache Kafka** (Jira plan, ADR-0018) and **this project itself** (ADR-0020); the platform is
> meant for any cross-functional release. The forecast is built and backtested. After
> recalibration it beats the historical base rate in 9 of 12 backtest cases but not all (see
> results), so the dashboard labels forecast odds "not validated".
> Numbers not in the results table are **TBD (not yet measured)**.
> What is done and what is left, phase by phase: [`docs/roadmap.md`](docs/roadmap.md).
> Operating the live deployment: [`docs/runbook.md`](docs/runbook.md).
> Security review of the public endpoints: [`docs/security-review.md`](docs/security-review.md).

### Plug in another team

Copy `connectors/teams/_template.yaml`, point at planning + code repos + a release calendar, pick a
`link_pack` (`kep` or `jira_key`), then `make backfill TEAM=<id> RELEASE=<name>`. Details:
[`connectors/teams/README.md`](connectors/teams/README.md) and ADR-0003.

## Architecture

```
Sources     Kubernetes GitHub (polled, 5 min) · Apache Kafka Jira (hourly) + GitHub (polled)
            · this repository (GitHub webhooks + poll)
              │
Collect     github_poller · jira collector · webhook receiver ──► normalized events
              │
Queue       Redis Streams (local) / Pub/Sub (cloud)  — trace context in message attributes
              │
Facts       linker → dependency graph + critical path → rule flags → Monte Carlo forecast
            → Portfolio rules (ADR-0025) · pod facts (ADR-0023) · Shadow-Org Simulator (ADR-0012)
              │
Store       Postgres (source of truth) + Redis (cache, live push)
              │
Serve       FastAPI (+ SSE) ──► Next.js (UX v1: Portfolio, Live Cockpit, Decision Studio, PDLC, Connect)
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
open http://localhost:3000  # front page → Portfolio, Live Cockpit, Decision Studio, AI-native PDLC, Connect
open http://localhost:16686 # Jaeger: traces from tpm-api and tpm-worker
```

API (all numbers computed by `engine/`; odds are labelled `validated: false` until a
backtest beats the base rate):

```bash
curl localhost:8000/portfolio                        # every live program: stage, bottleneck, next decision
curl localhost:8000/lab                              # this repository's pod facts (AI-native PDLC)
curl localhost:8000/releases
curl localhost:8000/releases/v1.38/features          # health table: odds, flags, linked PRs
curl localhost:8000/releases/v1.38/features/6395     # timeline, critical path, PRs, assumptions
curl localhost:8000/releases/v1.38/simulator         # Decision Studio inputs and the replay check
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

Dashboard (Next.js, `web/`, UX v1): Portfolio lists every live program. Live Cockpit is one
release (lifecycle, stat tiles, the #6395 time machine on Kubernetes v1.38, Code Freeze chart,
verified brief). The feature table, merge-date chart and dependency summary sit under "More
detail" on that page; Dependencies, Executive update and Link review are tabs. A feature page
shows its timeline (tracked, removed, re-added), critical path, PRs and the assumptions behind
the odds. Decision Studio is the simulator. AI-native PDLC reads `GET /lab`. Unlinked-PR load
per SIG is API-only. Pages refresh live over SSE when new data lands. The server renders with
`API_URL` (in-network); the browser opens the SSE stream at `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`).

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
| Linking coverage, Apache Kafka 4.4.0 (Jira plan, ADR-0018): features with ≥1 verified PR | **21 / 26 (81%)**, measured 2026-11-23; 89 links via sub-tasks; precision not labelled. `scripts/measure_kafka_linking.py` |
| PRs in the v1.38 window with a verified link | **609 / 2,757 (22.1%)**; 24 suggested-only; 2,124 unlinked (count as load) |
| Linking precision per method | TBD (not yet labelled): 70-row stratified v1.38 sample ready in `evals/cases/linking.csv` |
| Fact checker vs labelled claims (`make evals`) | **43 / 43 agree** (22 verified, 21 removed across all 5 reasons). Labels are proposed by the developer, pending TPM review. Measured 2026-11-22 |
| First real AI calls (`make ai-smoke`, Haiku 5.5, #6395 fact sheet) | `smoke.v1`: 9 verified / 10 removed, mostly a checker false positive on bare feature numbers ("feature 6395"), now fixed. `smoke.v2`: **16 verified / 1 removed** (a sentence stating uncited numbers). About **$0.001 per call**; repeat call served from cache at $0. Single runs, measured 2026-11-22; not an accuracy benchmark |
| Risk analyst live evals (12 real v1.37/v1.38 cases, Haiku 5.5, `risk_analyst.v4`) | **Removal rate 4.0%**, critical-flag coverage 100%, odds honesty 100%, 3–5 claims per note, $0.024 per run. Earlier prompts: v1 and v3 failed the gate; v2 passed it but was rejected after the notes were read (wrong wording). Measured 2026-11-22; small sample |
| VP summarizer live evals (4 real v1.37/v1.38 release fact sheets, Opus 5.5, `vp_summary.v1`) | **0% removed**, at most 217 words, top-3 at-risk coverage 100%, asks grounded 100%, odds honesty 100%; $0.54 per run (about $0.14 per draft). Measured 2026-11-22; small sample |
| Link suggester: shortlist recall (rule-linked PRs with keys hidden, no AI) | Right feature in the 12-item shortlist **88.1%** (v1.37, 1,040 PRs) and **86.8%** (v1.38, 949 PRs). Measured 2026-11-22; ADR-0011 |
| Link suggester live eval (60 hidden-key cases, Haiku 5.5, `link_suggester.v1`) | **Precision 84.8%**, recall 70%, false links on negatives 20%, 5.7% dropped by checks, $0.025 per run. Measured 2026-11-22; small sample |
| Link suggester on real v1.38 unlinked PRs | 1,797 unlinked → **104 suggestions** waiting for review, 1,636 "none", 11 dropped, 46 with no shortlist; **$0.54** in total. Reviewed precision: TBD (not yet reviewed). None of these count until a person confirms them |
| Simulator validation (replay with real arrivals and staffing, fitted only on earlier releases, ±20% on medians) | **Not validated.** With `/lgtm` and `/approve` comments counted as review activity, both releases fail on median review wait (v1.37 +205%, v1.38 +350%) and pass on time to merge (−12%, −5%). Measured 2026-11-22; ADR-0012. **Cause found 2026-11-25** (ADR-0012 addendum, PR #121): GitHub GraphQL drops `[bot]` from app logins, so Prow, EasyCLA and the Copilot reviewer counted as human reviewers. From v1.37, most PRs' "first review" is a bot comment within a minute. One re-run with those accounts excluded (in memory, model unchanged): **v1.37 passes (−5.5%), v1.38 fails (−41%)**. The data fix is PR #123 and needs a backfill. |
| Unlinked open PRs, Kubernetes v1.38 (summary tile) | **1,164 distinct** open PRs with no verified link (live API, 2026-11-25 01:02 UTC). The tile used to sum per-SIG counts (1,978 live on 2026-11-24; 1,956 vs 1,173 distinct on local data), which counted multi-SIG PRs twice. Fixed in #115 |
| AI-native PDLC: this repository's pod against its own rules (whole history, 68 PRs, 53 merged) | Merged agent PRs cross-reviewed **6 of 38**. Merged PRs with a human review or comment before merge **11 of 52** (an agent reply without its marker counts as human). Dependabot PRs closed unmerged **12 of 13**. PRs without exactly one risk tier **48 of 55**. Median open to merge **11 min**. Kept rate (30 days): TBD (first eligible 2026-12-22). The pod rules began 2026-11-24 (PR #91), so earlier PRs break them. Measured 2026-11-25 from GitHub data; PR #117 |
| Portfolio | Kubernetes v1.38 in Freeze (28 critical flags), Kafka 4.5.0 in Build (3 of 16 features with no linked code), this repository in Plan (review gap). Live values on 2026-11-24; `GET /portfolio` (ADR-0025) |
| Engine: assess all 106 v1.38 features from 60,230 events | project 0.22 s + assess 0.89 s (single run, laptop, Docker; not a p95) |
| API `/releases` (dashboard home), 162k events, 6 releases | cold cache **6.9 s**, warm 0.06 s (was several minutes cold: it forecast every release). Single runs, laptop, Docker; measured 2026-11-21, not a p95 |
| API v1.38 feature table, cold cache, 3 concurrent requests | **~21 s** each, sharing **one** computation (was one computation per request). Single run, measured 2026-11-21 |
| Merge-date forecasts (M7): 10th-90th range coverage and CRPS skill vs a baseline, v1.35-v1.37 at 28/14/7 days before freeze and 3 after | **Not validated.** With main-PR merge times (adopted in step 4): coverage 75-92%, CRPS skill > 0 in 3 of 12 cases, full rule passed in 2 of 12. Before step 4 the model was too pessimistic before freeze; v1.36/v1.37 release-day counts are now inside or near the range, v1.35 is too high. Rule fixed before the run; two backtest bugs corrected after the first run (ADR-0005). Measured 2026-11-22 |
| Odds with main-PR merge times (M7 step 4) vs all-PR merge times, v1.35-v1.38 × 3 lead times | Mean Brier **0.1885 vs 0.1897**, better in 9 of 12 (in-sample, adopted). Still beats the base rate in 9 of 12, so odds stay "not validated". Adding a per-stage non-code removal rate made Brier worse (0.1955) and was rejected. Measured 2026-11-22; ADR-0005 |
| API: requests over 2 s while polling v1.38 every 5 s for 11 min (crosses 2 cache expiries) | Before **2** (one per expiry, worst 23 s). After stale-while-revalidate **0** from expiries; 1 cold start right after a redeploy (29.6 s). p50 ≤ 0.12 s both. Measured 2026-11-22; ADR-0002 |
| Unseen test: v1.39 scored on forecasts recorded daily while it runs (model `forecast-m7.1+1a53f2d9`, frozen 2026-11-22) | TBD (not yet measured): v1.39 has not started. Rules and model fixed in ADR-0015; snapshots are append-only (a Postgres trigger refuses edits) |
| Data freshness (polled Kubernetes, target < 10 min) | **Under 9 min worst case**: 24 of 24 polls succeeded every 5 min; longest gap between successful polls 6.2 min, poll run 74 s p50 / 124 s max. Measured 2026-11-23 20:02-22:03 UTC; `docs/results/poll-freshness-cloud-20261123.json` |
| Stored event → live page in the cloud (p95), polled data | **15.9 s** (p50 12.7 s, n = 122 pushes, 2 open pages); v1.38 recompute p95 **9.2 s** (was about 56 s). Excludes the wait for the next poll. Measured 2026-11-23, 2-hour window, small sample; ADR-0019 |
| Event → dashboard latency via webhooks (p95, target < 30 s) | **9.7 s: passes** (p50 5.7 s, max 12.2 s; n = 27 webhook events, each timed from GitHub's event time to the first push to an open page). GitHub's delivery p50 2.2 s, receipt → page p50 3.6 s. Measured 2026-11-24 04:29–04:45 UTC with Kubernetes, Kafka and webhooks flowing, after the P3-M5 fixes; before them some events took 60 s to 14 min (ADR-0022). Small sample, one repository. `docs/results/webhook-latency-cloud-20261124T044532Z.json` |
| Simulator: one what-if scenario (target p95 < 2 s) | **Server p95 1.39 s** (p50 1.34 s, max 3.06 s; 9 of 10 runs under 2 s). n = 10 scenarios run one after another on the live API, 2026-11-24; small sample. `docs/results/load-test-cloud-20261124.json` |
| API under load: 10 then 20 users | **0 errors; server p95 0.53 s at 31 requests/s** (client p95 0.65 s), after caching the dependency graph off the event loop (#74). Before: p95 about 2 s at 12 requests/s. 2026-11-24; no recompute ran during the final run (#70). `docs/results/load-test-cloud-20261124-after.json` |
| Database restore (point-in-time clone) | **Pass**: 9 minutes; schema and every row count up to the restore point matched production. 2026-11-24. `docs/results/restore-test-20261124.json` |

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
- **M3b done: VP summarizer and TPM approval** (ADR-0010). Live Cockpit links to it as
  **Review exec update**; the page is the Executive update tab. Opus drafts about 200 words
  in Summary / At risk / Removed / Asks, using
  only verified claims; asks come from fixed rules. The TPM edits (edits are re-checked),
  then approves or rejects, recorded as "Harpreet (local, unauthenticated)". Nothing is
  ever sent: approved updates offer "Copy as Markdown".

- **M4 done: AI link suggester and review queue** (ADR-0011). Code shortlists 12 features
  for each unlinked PR. Haiku picks one or says none, quoting both sides, and the quotes
  are checked word for word. The Link review tab lists suggestions; only a
  person's confirmation makes a link count. `make suggest-links RELEASE=v1.38` runs it
  within the daily budget.
- **M5: what-if simulator, shipped not validated** (ADR-0012). SimPy model of PRs
  queueing for SIG reviewer pools, fitted on earlier releases and validated by replay.
  With PR comments counted as review activity it fails on both v1.37 and v1.38 (review
  wait far too long), so it is **not validated**.
  - Decision Studio (**Test a fix** on Live Cockpit) lets you change reviewers, new reviewers and
    ramp-up, interruptions and the flow of new PRs per SIG pool.
  - It shows baseline vs scenario until the next milestone, as ranges over 8 seeded
    runs. Scenarios can be saved and compared.
  - Every result carries a "not validated" banner.
  - A scenario request takes p95 0.86 s (40 requests, local Docker, measured
    2026-11-22).
  - `make sim-calibrate RELEASE=v1.38` fits and stores the calibration.
- **M6: dashboard redesign** (ADR-0013), in light colours, based on the owner's mockup.
  UX v1 (ADR-0024) replaced the sidebar and the Overview / Release health menu. The
  screenshots are this layout, on 2026-11-22, local Docker, real public data.

  ![Earlier front page: pipeline steps and a live pulse of Kubernetes v1.38](docs/images/front-page.png)

  ![Earlier v1.38 dashboard: sidebar, stat tiles, dependencies, Code Freeze outcomes, verified brief](docs/images/dashboard-v1.38.png)

  - A sidebar, five stat tiles, and a summary of how features depend on each other.
  - A Dependencies page (rebuilt, see the ADR-0013 addendum): groups of features that share
    verified PRs or state a "depends on", a map with a per-feature side panel, open PRs
    waiting on an unmerged PR, and SIGs that share features. In v1.38: 28 of 70 features
    are tied to another, in 3 groups.
  - A chart of what happened at Code Freeze, or each feature's odds before it.
  - The newest executive brief: approved, or clearly marked as a draft, with every line
    fact-checked.
  - Not copied from the mockup: the days-of-delay curve and "reallocate TPMs" lines,
    because nothing computes them. The curve is a candidate for M7.
- **Front page** at `/` (phase 2): what the product does, how the pipeline splits
  deterministic code, AI and human approval, a live pulse of the current release, and a
  scorecard of measured results, including failures. UX v1 replaced that page. The current
  front page is the screens table above. `/releases` is still All releases.
- **M7 (forecast improvements).**
  - Release views are served from the cache while they recompute in the background. A
    cache expiry no longer makes anyone wait (ADR-0002 addendum).
  - Merge dates: when each feature's required code will merge, before or after Code
    Freeze, and a "When will the remaining code merge?" chart (the days-of-delay curve
    from the mockup). **Not validated** (ADR-0005).
  - Merge times now come from main PRs only, a small in-sample gain for odds and merge
    dates. A per-stage non-code removal rate was tested and rejected.
  - Every forecast is recorded daily in append-only tables, with its model version
    (ADR-0015). v1.39 will be the first test on a release the model has never seen:
    `make score-snapshots RELEASE=v1.39` once it finishes.
- **Multi-project navigation** (ADR-0014): release URLs carry the project
  (`/projects/kubernetes/releases/v1.38`; old `/releases/v1.38` links redirect).
  The switcher is the Portfolio / program breadcrumb on Live Cockpit and Decision Studio.
  Portfolio is the cross-program screen. `/releases` lists every collected release.
  Apache Kafka (ADR-0018) and this project (ADR-0020) are shown alongside Kubernetes.

## Limitations

- **Lean cloud deployment** (option B, ADR-0017): one API instance running the worker, no
  Redis, shared-core Cloud SQL. Live since 2026-11-23. The deploy workflow rolls out new
  images only; Terraform changes are applied by hand. The cloud poller failed every run
  from the first deploy until 2026-11-23 20:00 UTC (no Cloud SQL socket with a sidecar
  container), so the site showed the loaded data without new events until then.
- **Webhooks cover this repository only** (P3-M5, ADR-0020). A repository webhook delivers
  its events in seconds (p95 9.7 s, small sample). Kubernetes and Kafka stay polled every
  5 minutes (the Kafka plan hourly), since webhooks need admin rights on the source
  repository.
- **Who reviewed, in this repository, comes from a marker line, not the login** (ADR-0023
  addenda). Every agent and the owner post from the owner's GitHub account, so agents start
  each review with `Cross-review · <lane>`. An agent comment without the marker counts as the
  owner's review. First-pass approval cannot be measured: GitHub does not let a PR's author
  approve it. The lab is a case study of tool lanes on this repository, not a ranking of
  people, and a what-if comparison waits until 20 pull requests have merged.
- **Bot accounts read through GraphQL** were stored without `[bot]` until PR #123, so Prow,
  EasyCLA and the Copilot reviewer counted as human review activity in the polled data
  (ADR-0012 addendum). Review-round numbers for Kubernetes and Kafka are affected until the
  fix is merged and the data is backfilled.
- **This project has no history yet** (ADR-0020). Its `Phase 3` release begins on
  2026-11-30 and has no earlier release to learn from, so its forecasts say "not enough
  history" instead of a number (#9).
- **Phase 3 M1: sign-in and permissions** (ADR-0016). Reading is public. Drafting or
  approving executive updates, deciding AI link suggestions, saving scenarios, and
  generating risk notes with paid AI need a GitHub sign-in on the approver allowlist.
  Approvals record the GitHub login. Actions are signed by the web server and checked by
  the API; a missing configuration fails closed. Real GitHub sign-in needs an OAuth app
  (see `.env.example`); local development uses `AUTH_MODE=local`.
- Phase 2 is done: fact checker, AI gateway, risk analyst, VP summarizer with TPM approval, the AI link suggester with a review queue, a what-if simulator (not validated), the redesigned dashboard and forecast improvements. Phase 3 so far: sign-in (M1), Jira for Kafka, cloud deploy, faster recompute (M4, measured in the cloud). Phase 3 M5 (webhooks end to end, measured) and M6 (operations) are done; follow-ups are tracked in `docs/roadmap.md`.
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
- **API recompute is not incremental.** Each change to the data re-projects every stored event.
  With linking shared and the calibration cached (ADR-0019) a v1.38 recompute takes 9.2 s p95
  in the cloud (2026-11-23). Fine for polled data; heavy webhook traffic is untested.
- **CI flags cannot tell required checks from optional ones.** Prow does not mark them in the
  API data we read, so `ci_failing` counts any failing check on the latest commit.
- Release dates come from a checked-in calendar
  (`collectors/github_poller/release_calendar.yaml`) with a source link per release. The
  v1.36 and v1.37 release days have no time of day in the source, so they are stored as 00:00 UTC.

## Design decisions

See [`docs/decisions/`](docs/decisions/).

## Data

Public Kubernetes data only. The platform measures flow and bottlenecks, not individual performance.
