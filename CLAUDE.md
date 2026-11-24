# CLAUDE.md — Program Intelligence Platform

This file is the permanent source of project rules. Read it at the start of every session and follow it for every change.

## 1. What we are building

A production-grade, real-time platform that predicts which features in a large multi-team software release will slip, explains why, and drafts the executive update.

- **The plan** comes from planning tickets: GitHub enhancement issues (Kubernetes) or Jira epics/stories (Apache Kafka, companies).
- **The truth** comes from the code: PRs, reviews, CI, merges.
- The platform **links** them (PR → feature/story → epic → release), computes the facts, forecasts the odds, lets leaders run what-if scenarios, and uses AI only to explain. Every AI claim is verified before anyone sees it, and a human approves the executive update.

Owner: Harpreet Dhindsa (TPM leader). This is a public portfolio project with a live demo. Code quality, clarity, and honest measured results matter more than feature count.

## 2. Core principles (never break these)

1. **AI never computes facts.** Counts, dates, durations, links with explicit evidence, critical paths, and odds are computed by deterministic code or statistics. AI is used only for messy text and judgment (explanations, summaries, link *suggestions*).
2. **If an AI mistake could change the facts, AI only suggests.** AI-suggested links are stored as `suggested` until a rule verifies them or a person confirms them.
3. **Every AI output is structured and verified.** Agents return Pydantic models of individual claims. The fact checker verifies each claim against the database. Unverifiable claims are removed and counted.
4. **Humans approve.** The platform never sends anything on its own. Executive updates require TPM approval.
5. **Measure, don't claim.** Accuracy, hallucination rate, linking coverage, latency, and cost are measured and published. Placeholder numbers must be labeled as placeholders.
6. **Observability from day 1.** Every service is instrumented with OpenTelemetry from its first commit.
7. **Public data only.** Use only public Kubernetes and Apache Kafka data, plus a sample Jira Cloud site. Never use or reference any employer's code, data, or documents.

## 3. Architecture (event-driven, Google Cloud)

```
Sources:   Kubernetes (GitHub, polled) | Team repos (GitHub App webhooks) | Jira (REST API + webhooks)
Collect:   poller (Cloud Scheduler) | webhook receiver (Cloud Run) | jira collector
Queue:     Pub/Sub (trace context carried in message attributes)
Facts:     linker → dependency graph + critical path → rule flags → Monte Carlo forecast → SimPy simulator
AI:        LangGraph agents (link suggester, risk analyst, VP summarizer, Jira comment summarizer)
Verify:    fact checker + eval suite
Store:     Postgres (source of truth) + Redis (cache, live push)
Serve:     FastAPI (API, simulator, permissions) + Next.js web app (SSE live updates)
Operate:   OpenTelemetry, Langfuse, Secret Manager, Terraform, GitHub Actions
```

Collectors emit **normalized events**. Downstream code never depends on which source an event came from.

## 4. Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, httpx
- **Engine:** NetworkX, NumPy, pandas; **simulator:** SimPy
- **AI:** Anthropic Claude API (model names come from config, never hard-coded), LangGraph, Pydantic structured output, Langfuse tracing
- **Data:** PostgreSQL, Redis
- **Frontend:** Next.js (App Router), React, TypeScript, Tailwind, React Flow, Recharts, Auth.js (GitHub sign-in)
- **Infra:** Docker, Docker Compose (local), Terraform, Google Cloud Run, Pub/Sub, Cloud SQL, Memorystore, Secret Manager, Cloud Scheduler
- **Observability:** OpenTelemetry SDK + Collector → Cloud Trace / Monitoring / Logging
- **Quality:** pytest, ruff, mypy (strict for `engine/`, `linker/`, `verify/`), eslint, GitHub Actions

## 5. Repo layout

```
tpm-intelligence/
  README.md  CLAUDE.md  docker-compose.yml  .env.example
  docs/decisions/        # ADRs: one per design decision (ADR-0001-*.md)
  collectors/            # github_poller/, github_webhooks/, jira/
  pipeline/              # normalized event schema, Pub/Sub publish/consume helpers
  linker/                # PR → work item → release
  engine/                # graph, critical_path, rules, forecast
  simulator/             # SimPy org model
  agents/                # LangGraph agents + prompts
  verify/                # fact checker
  evals/                 # labeled cases, scoring, run_evals.py
  api/                   # FastAPI service
  web/                   # Next.js app
  infra/                 # Terraform
  observability/         # OTel collector config, dashboards, alert policies
  scripts/               # backfill, seed demo data
  tests/                 # unit + integration tests mirroring the package layout
```

## 6. Data model rules

- Use a generic **WorkItem** (`type`: initiative | epic | feature | story | subtask | bug; `parent_id`; `source`: github | jira; `external_key`).
- **Work items ↔ releases are many-to-many.** One ticket can ship in several releases (real example: KAFKA-21181 lists fix versions 4.0.0, 4.1.0, 4.2.0, 4.3.0).
- **Links carry a method and a confidence level:** `explicit_key` (KEP number / Jira key) > `tracking_issue_link` > `remote_link` > `feature_gate` > `labels` > `ai_suggested`. AI links stay `suggested` until verified.
- **Store history as timestamped snapshots/events.** Backtests may only use data dated before the prediction point.
- **Removed items disappear from current-state searches.** Use issue event history (milestoned/demilestoned, tracked/yes → tracked/no) to know what was removed and when.
- **Count review rounds, not raw review records.** One reviewer can submit 40+ review comments in one sitting; group by reviewer within a time window.
- **Unlinked PRs still count** as reviewer and CI load.
- **Code counts for a release** if merged before Code Freeze, or later with an approved exception.
- **Jira statuses** map to standard states using Jira's built-in status categories (To Do / In Progress / Done), with per-team overrides.

## 7. External API rules

- **GitHub:** token from env `GITHUB_TOKEN` (read-only). Prefer GraphQL for nested data. **Issue history (milestone/label/close events) comes from GraphQL `timelineItems`**: the REST issue events and timeline endpoints are capped at about 300 items and drop the newest events on long-lived KEPs (verified 2026-11-21 on #3157, #4815, #2570). Incremental sync with `updated_at` cursors. Respect rate-limit headers and back off.
- **Jira (Apache):** `https://issues.apache.org/jira/rest/api/2/` works anonymously. Apache rate-limits automated tools with **HTTP 429** (about 2 minutes). Sync slowly, cache, honor 429 with backoff. **Never scrape Jira web pages; API only.**
- All HTTP calls go through one client wrapper with retries, backoff, timeouts, and OTel spans.

## 8. AI rules

- Agents only receive engine facts as input. Prompts live in `agents/prompts/` as versioned files.
- Outputs are Pydantic models of claims, e.g. `Claim(text, type, refs, value)`.
- The fact checker verifies every claim: matching value → `verified`; wrong value → `removed`; no supporting data → `removed`. Store counts.
- Run AI only when facts change meaningfully (configurable thresholds, e.g. odds change ≥ 10 points). Cache by a hash of the input facts.
- Route simple tasks to a cheaper model and summaries to a stronger one (both via config). Enforce a daily budget cap: slow down at 80%, pause non-essential AI at 100%.
- Any prompt or model change must pass `evals/` before merge.

## 9. Observability rules

- Every service: OTel tracing, metrics, structured JSON logs with trace IDs.
- Propagate trace context through Pub/Sub message attributes so one trace spans webhook → dashboard.
- SLOs (starting targets): data freshness < 10 min (polled); event→dashboard p95 < 30 s (webhooks); simulator p95 < 2 s; availability 99.5%; AI spend under the daily cap.
- Alerts: queue backlog growing, 2 failed polls in a row, unusual fact-checker removal rate, AI spend at 80%.

## 10. Security rules

- No secrets in code or in git. Local: `.env` (gitignored) with `.env.example` committed. Cloud: Secret Manager.
- Read-only scopes for GitHub and Jira. Store only needed fields; never store source code.
- Per-team data isolation; users only see work items they can see in the source system.
- The platform measures flow and bottlenecks, **not individual performance**. Do not build per-person productivity rankings.

## 11. Coding standards

- Small, focused modules with type hints and docstrings on public functions.
- Pure functions in `engine/`, `linker/`, `verify/`, and `simulator/` (no I/O), so they are easy to test.
- Every bug fix adds a test. Every new rule or linking method adds tests with real-shaped fixtures.
- Use these **real examples as test fixtures** (store trimmed JSON in `tests/fixtures/`):
  - Kubernetes enhancement **#6395** "Dynamic node-local ephemeral volumes" (sig/node, sig/storage, alpha, v1.38; kep.yaml under `keps/sig-storage/`, feature gate `DynamicNodeLocalEphemeralVolumes`): opted in Sep 21, tracked Sep 23, **removed at Code Freeze Nov 17, 2026 12:05 UTC**, re-added Nov 21. k/k PRs listed in the issue description (the release team's tracking list): #143442 (closed, **not merged**), #143445 (merged Oct 27), #143474 (merged Nov 6), #143522 (merged Nov 4), **#143709 main implementation (opened Nov 2, merged Nov 20 23:28 UTC, after Code Freeze)**. **#143644** (merged Nov 6) mentions #6395 only in passing ("as discussed in") and is mainly KEP #1432 work: the test case for a passing mention that must stay `suggested`. Verified against the live API on 2026-11-21. The issue timeline has **no** cross-reference events, so PRs are found from the issue description and PR text, not the timeline.
  - Kubernetes v1.38: Enhancements Freeze Sep 30, 2026 12:00 UTC; Code Freeze Nov 17, 2026 12:00 UTC; release Dec 16, 2026.
  - Kubernetes enhancement **#2570** (long-lived KEP, history over 300 REST events): **removed at Code Freeze Nov 17, 2026 12:38 UTC**, re-added Nov 21 02:12 UTC. The REST events API misses this entirely; it is the regression fixture for the GraphQL timeline rule in section 7.
  - **KAFKA-19831**: links to KAFKA-17789; Fix Version changed 3 times in its history.
  - **KAFKA-21181**: status In Progress while tagged with released fix versions 4.0.0–4.3.0 (status drift + many-to-many releases).

## 12. How to work in this repo

Branch and pull-request rules for every coding agent and the owner live in `AGENTS.md`. Follow that file. Do not push to `main`.

1. **Plan before coding.** For any task bigger than a small fix, write a short plan (files, steps, tests, risks) and wait for approval.
2. Work in **small, reviewable steps.** After each step: run `ruff`, `mypy`, `pytest`, and relevant evals; fix failures before moving on.
3. **Record design decisions** as ADRs in `docs/decisions/` (context, decision, alternatives, trade-offs). Explain every AI-vs-rules choice there.
4. Keep `README.md` current: problem, architecture diagram, how to run, measured results (labeled clearly), limitations.
5. Never invent results. If a number is not measured yet, write "TBD (not yet measured)".
6. When unsure about a requirement, ask instead of guessing.
7. At the end of each step, summarize: what changed, how it was tested, what is next.

## 13. Commands

```
docker compose up -d          # Postgres, Redis, OTel collector, services
make test                     # ruff + mypy + pytest
make evals                    # AI eval suite
make backfill RELEASE=v1.38   # load Kubernetes release data
alembic upgrade head          # apply DB migrations
```
(Create the Makefile targets as part of phase 1.)

## 14. Simulator rules (Shadow-Org Simulator)

The simulator answers "what happens if we change something?" It must be credible enough for a leader to act on.

- **Calibrated on real data only.** Inputs come from measured distributions in the database: PR arrival rate per week, review rounds per PR, wait per review round, time to merge, reviewer workload (including unlinked PRs), interruption rate. Store each calibration with its source release range and date (e.g. "v1.35–v1.37, measured 2026-11-21"). With Jira: cycle time, throughput and sprint velocity per team.
- **Validate before use.** Replay a past release with its real staffing and check that the simulated review waits and merge times match the actual ones within a set tolerance (start with ±20% on the median; record the result). If validation fails, the UI shows the simulator as "not validated" and does not present what-ifs as reliable.
- **Model:** SimPy discrete-event simulation. Reviewers are resources; PRs are arrivals; review rounds are service time; interruptions remove reviewer capacity; new engineers ramp up over a configurable period. Output feeds the Monte Carlo forecast, which produces release and feature odds.
- **Ranges, never single certainties.** Run multiple replications and show a range (e.g. "38%, likely 30–46%"). Use fixed random seeds for reproducible results in tests and demos.
- **Baseline vs scenario.** Always show the current baseline next to the scenario, with the difference highlighted (odds, features likely to slip, review wait per queue).
- **Visible assumptions.** Every result lists the measured inputs it used and their source releases.
- **Scenarios are saved and comparable.** Users can name, save, reload and compare scenarios. A "suggested fix" can be applied and re-run.
- **No AI in the numbers.** AI may describe a scenario result in words, but every number comes from the simulator and forecast, and the fact checker verifies any claim about it.
- **Fast.** p95 under 2 seconds for a standard scenario (cache calibrations; limit replications for interactive use, run more in the background).
- **Honest language.** Results are decision support ("if these assumptions hold, odds are likely X"), never guarantees.
