# CLAUDE.md — Program Intelligence Platform

This file is the permanent source of project rules. Read it at the start of every session and follow it for every change. `README.md` holds the current status and measured results; this file holds the rules.

## 1. What we are building

**An AI-native, end-to-end program management platform that a company plugs into its own tools.** It runs the routine parts of program management continuously (tracking, bottlenecks, risks, dependencies, decisions, forecasts, stakeholder updates, launch readiness, retros) so TPMs spend their time on judgment and decisions.

- **The plan** comes from planning tools: GitHub issues (Kubernetes), Jira (Apache Kafka, most companies), later Linear and others.
- **The truth** comes from the work: PRs, reviews, CI, merges, and later meeting notes and incidents.
- The platform **links** them (PR → feature/story → epic → release → program), computes the facts, forecasts the odds, lets leaders run what-ifs, and uses AI only to read messy text and explain. Every AI claim is verified before anyone sees it, and a human approves anything that leaves the platform.

**Why now.** AI writes code at machine speed, but people still review and verify it at human speed. The bottleneck has moved from writing code to reviewing, verifying and integrating it. The platform must show where delivery is really stuck: review capacity, review depth, rework and churn, not only "will we ship on time".

**Proof datasets, not the product.** Kubernetes (GitHub planning), Apache Kafka (Jira planning) and this repository itself (ADR-0020) prove that any team can plug in. The product is for any cross-functional program.

Product name: **Program Intelligence Platform** (renamed from TPM Intelligence, ADR-0021). Tagline: "AI-native program management · every fact verified". Owner: Harpreet Dhindsa (TPM leader). This is a public, open-source portfolio project with a live demo. Code quality, clarity and honest measured results matter more than feature count.

## 2. Core principles (never break these)

1. **AI never computes facts.** Counts, dates, durations, links with explicit evidence, critical paths, odds and metrics are computed by deterministic code or statistics. AI is used only for messy text and judgment (explanations, summaries, extraction, link and item *suggestions*).
2. **If an AI mistake could change the facts, AI only suggests.** AI-suggested links, RAID items, merges and dependencies are stored as `suggested` until a rule verifies them or a person confirms them.
3. **Every AI output is structured and verified.** Agents return Pydantic models of individual claims. The fact checker verifies each claim against the database (or, for extracted text, against a verbatim quote of the source). Unverifiable claims are removed and counted.
4. **Humans approve.** The platform never sends, posts or changes anything in a source system on its own. Executive updates, published RAID trackers and readiness decisions require TPM approval.
5. **Measure, don't claim.** Accuracy, hallucination rate, linking coverage and precision, latency and cost are measured and published, including failures. Unmeasured numbers say "TBD (not yet measured)". Unvalidated models are labeled "not validated" in the UI.
6. **Observability from day 1.** Every service and every new module is instrumented with OpenTelemetry from its first commit.
7. **Public data only.** Use only public Kubernetes and Apache Kafka data, this repository, a sample Jira Cloud site, and public or clearly labeled synthetic meeting notes. Never use or reference any employer's code, data or documents.
8. **Flow, not people.** The platform measures flow and bottlenecks by team, pool or SIG, never individual performance. No per-person productivity rankings, and no AI-vs-human comparisons about named people.
9. **Plug in, don't fork.** A new team, company or tool is added through a connector and configuration. Core packages (`engine/`, `pipeline/`, `verify/`, `api/`) never change for one customer.

## 3. Architecture (event-driven, Google Cloud)

```
Connect:   connectors (GitHub, Jira; next: meeting notes, GitLab, Linear, Slack, incidents) + per-team/per-tenant config
Collect:   pollers (Cloud Scheduler) | webhook receivers (Cloud Run) → normalized events
Queue:     Pub/Sub in the cloud, Redis Streams locally (trace context in message attributes)
Core:      work-item model + linker + history/snapshots + permissions
Facts:     dependency graph + critical path → rule flags → delivery signals → Monte Carlo forecast → SimPy simulator
Modules:   live tracking | bottleneck radar | RAID tracker | forecast | simulator | stakeholder updates | release readiness | retro insights
AI:        LangGraph agents (link suggester, risk analyst, VP summarizer, RAID extractor, readiness and retro writers)
Verify:    fact checker + eval suite → human approval
Store:     Postgres (source of truth) + Redis (cache, live push)
Serve:     FastAPI (API, simulator, permissions) + Next.js web app (SSE live updates)
Operate:   OpenTelemetry, Langfuse, Secret Manager, Terraform, GitHub Actions
```

- Collectors emit **normalized events**. Downstream code never depends on which source an event came from.
- **Modules read the shared core; they never read a source system directly.** A module that needs new data gets it through a connector and the event pipeline.
- The current cloud deployment is the lean option in ADR-0017 (one API instance running the worker, no Redis, shared-core Cloud SQL). Scale up only with a new ADR.

## 4. Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, httpx, uv
- **Engine:** NetworkX, NumPy, pandas; **simulator:** SimPy
- **AI:** Anthropic Claude API (model names come from config, never hard-coded), LangGraph, Pydantic structured output, Langfuse tracing
- **Data:** PostgreSQL, Redis
- **Frontend:** Next.js (App Router), React, TypeScript, Tailwind, React Flow, Recharts, Auth.js (GitHub sign-in)
- **Infra:** Docker, Docker Compose (local), Terraform, Google Cloud Run, Pub/Sub, Cloud SQL, Memorystore (optional), Secret Manager, Cloud Scheduler
- **Observability:** OpenTelemetry SDK + Collector → Jaeger (local) / Cloud Trace, Monitoring, Logging (cloud)
- **Quality:** pytest, ruff, mypy (strict for `engine/`, `linker/`, `verify/`, `simulator/`), eslint, vitest, GitHub Actions

## 5. Repo layout

```
tpm-intelligence/
  README.md  CLAUDE.md  LICENSE  docker-compose.yml  .env.example  Makefile
  docs/decisions/        # ADRs: one per design decision (next free number: see docs/plan/e2e-plan.md, reserved per wave)
  docs/ux/               # locked UX spec (ux-v1-locked.md)
  docs/pod/              # pod rules (RULES.md) for people, AI agents and bots
  docs/plan/             # e2e-plan.md: the waves, owners and reserved ADR numbers
  docs/results/          # measured result files referenced by the README
  connectors/            # teams/<id>.yaml configs, schema, loader (ADR-0003)
  collectors/            # github_poller/, github_webhooks/, jira/ (next: notes/, gitlab/, linear/)
  pipeline/              # normalized event schema, queue (Pub/Sub / Redis Streams), worker, store
  linker/                # PR → work item → release; packs/ per planning style (kep, jira_key, github_issue)
  engine/                # graph, critical path, rules, delivery signals, forecast, backtests
  simulator/             # SimPy org model, calibration, replay
  modules/               # (new) one package per module that is not core: raid/, readiness/, retro/
  agents/                # LangGraph agents + versioned prompts/
  verify/                # fact checker
  evals/                 # labeled cases, scoring, run_evals.py
  api/                   # FastAPI service
  web/                   # Next.js app
  infra/                 # Terraform
  observability/         # OTel collector config, dashboards, alert policies
  scripts/               # backfill, measurement and backtest scripts
  tests/                 # unit + integration tests mirroring the package layout
```

## 6. Data model rules

- Use a generic **WorkItem** (`type`: program | initiative | epic | feature | story | subtask | bug; `parent_id`; `source`: github | jira | …; `external_key`).
- **Work items ↔ releases are many-to-many.** One ticket can ship in several releases (real example: KAFKA-21181 lists fix versions 4.0.0, 4.1.0, 4.2.0, 4.3.0).
- **Links carry a method and a confidence level:** `explicit_key` (KEP number / Jira key) > `tracking_issue_link` > `remote_link` > `feature_gate` > `labels` > `ai_suggested`. AI links stay `suggested` until verified.
- **Store history as timestamped snapshots/events.** Backtests may only use data dated before the prediction point. Forecast snapshots are append-only (ADR-0015).
- **Discover every item that was ever in a release, not just the ones in it now.** Features removed at a freeze lose their milestone. Build the candidate list from issue history (milestoned to the release, `lead-opted-in`, `tracked/yes` / `tracked/no`) and `kep.yaml` milestone fields, then dedupe.
- **Count review rounds, not raw review records.** One reviewer can submit 40+ review comments in one sitting; group by reviewer within a time window.
- **Unlinked PRs still count** as reviewer and CI load.
- **Code counts for a release** if merged before Code Freeze, or later with an approved exception.
- **Jira statuses** map to standard states using Jira's built-in status categories (To Do / In Progress / Done), with per-team overrides.
- **All timestamps are stored in UTC.** Deadlines are compared in UTC; the UI converts to the viewer's time zone.
- **As-of replay.** Every view can be computed "as of" a past date using only data available then.
- **Text fields are today's text** where the source does not version them (issue descriptions, PR bodies, `kep.yaml`). Backtests must not depend on text that could have changed late.

### Delivery signals for AI-accelerated teams

- **AI assistance is detected only from what contributors disclose** (PR description statements, commit trailers, bot or app authors), using patterns from the team's connector config. Kubernetes requires a disclosure statement in the PR description (policy updated April 2026). Report the AI-assisted share as a **minimum**, with the detection rule shown, and only for PRs created after the team's policy date.
- **Time to first review** = PR ready for review → first human review action. Bot and AI-reviewer actions are counted separately, never as human review.
- **Review capacity** = review rounds completed per week per reviewer pool, compared with review demand (rounds needed by open and arriving PRs). Report by pool or SIG, never by person.
- **Review depth:** review rounds before merge, and PRs merged with zero or one human review action.
- **Rework and churn:** reverts (revert PRs and revert commits), follow-up fix PRs that reference a merged PR, and changes to the same files within 30 days of a merge. Define each rule in an ADR before computing it.
- **PR size:** lines and files changed, with generated and vendored files excluded by a rule.
- **Minimum group size:** any comparison (for example AI-assisted vs other PRs) is shown only for groups of at least 10 PRs, so no individual can be identified.

### RAID items (risks, actions, issues, decisions)

- Every RAID item has a deterministic ID `{WORKSTREAM}-{TYPE}-{SEQ}` (types: R risk, A action, I issue, D decision, Q question) that never changes, so it can be traced across meetings.
- Each item stores its source (meeting, ticket, PR), a verbatim quote from that source, owner (a role or team in the public demo), status and lifecycle history (open → in progress → closed / superseded).
- AI extracts and suggests merges; the quote must match the source word for word; items stay `suggested` until a TPM confirms them. Merge and dedupe decisions are stored with their reason.

## 7. External API rules

- **GitHub:** token from env `GITHUB_TOKEN` (read-only). Prefer GraphQL for nested data. **Issue history (milestone/label/close events) comes from GraphQL `timelineItems`**: the REST issue events and timeline endpoints are capped at about 300 items and drop the newest events on long-lived KEPs (verified 2026-11-21 on #3157, #4815, #2570). Incremental sync with `updated_at` cursors. Respect rate-limit headers and back off. The search API has much lower limits: search narrowly and cache. Read `kep.yaml` from the kubernetes/enhancements repo, never by scraping.
- **CI data:** Prow does not mark required vs optional checks in the API data we read, so `ci_failing` counts any failing check on the latest commit. Say so wherever CI is shown.
- **Jira (Apache):** `https://issues.apache.org/jira/rest/api/2/` works anonymously. Apache rate-limits automated tools with **HTTP 429** (about 2 minutes). Sync slowly, cache, honor 429 with backoff. **Never scrape Jira web pages; API only.**
- **New sources:** before building on a new source (meeting notes, GitLab, Linear, incidents), verify with real API calls what data is available, its rate limits and its terms of use. Record the evidence in an ADR. If data is missing, ship without that feature and say so.
- All HTTP calls go through one client wrapper with retries, backoff, timeouts and OTel spans.

## 8. AI rules

- Agents only receive engine facts (or the specific source text being extracted) as input. Prompts live in `agents/prompts/` as versioned files.
- Outputs are Pydantic models of claims, e.g. `Claim(text, type, refs, value)`.
- The fact checker verifies every claim: matching value → `verified`; wrong value → `removed`; no supporting data → `removed`. Extracted text must quote the source verbatim. Store counts.
- Run AI only when facts change meaningfully (configurable thresholds, e.g. odds change ≥ 10 points). Cache by a hash of the input facts.
- Route simple tasks to a cheaper model and summaries to a stronger one (both via config). Enforce the daily budget cap (currently $2/day): slow down at 80%, pause non-essential AI at 100%.
- Any prompt or model change must pass `evals/` before merge. Every new agent ships with a labeled eval set and a gate in CI.

## 9. Observability rules

- Every service: OTel tracing, metrics, structured JSON logs with trace IDs.
- Propagate trace context through queue message attributes so one trace spans source event → dashboard.
- SLOs (starting targets): data freshness < 10 min (polled); event→dashboard p95 < 30 s (webhooks); simulator p95 < 2 s; availability 99.5%; AI spend under the daily cap.
- Alerts: queue backlog growing, 2 failed polls in a row, unusual fact-checker removal rate, AI spend at 80%, cloud billing budget thresholds.
- Alert policies and dashboards are defined in code (Terraform), not by hand.

## 10. Security and privacy rules

- No secrets in code or in git. Local: `.env` (gitignored) with `.env.example` committed. Cloud: Secret Manager. CI: GitHub Actions secrets.
- Read-only scopes for every source. Store only needed fields; never store source code.
- **Per-tenant and per-team isolation**, enforced in the API and the database (row-level security once there is more than one tenant). Users only see work items they can see in the source system.
- Reading the public demo is open; any action that costs money or changes state (paid AI, approvals, link decisions, saved scenarios) needs sign-in on the approver allowlist (ADR-0016). Missing configuration fails closed.
- **Public demo privacy:** Kubernetes and Kafka data involve real contributors. Explanations and charts use roles and counts ("one reviewer pool owns 6 open PRs"), not GitHub or Jira usernames. Usernames may be stored for computation but are not displayed publicly.
- **Cost guardrails:** Cloud Run scales to zero, but Cloud SQL (and Memorystore, if used) has always-on cost. Use the smallest tiers for the demo and keep a billing budget with alerts.

## 11. Coding standards

- Small, focused modules with type hints and docstrings on public functions.
- Pure functions in `engine/`, `linker/`, `verify/`, `simulator/` and module logic (no I/O), so they are easy to test.
- Every bug fix adds a test. Every new rule, signal, linking method or connector adds tests with real-shaped fixtures.
- Use these **real examples as test fixtures** (store trimmed JSON in `tests/fixtures/`):
  - Kubernetes enhancement **#6395** "Dynamic node-local ephemeral volumes" (sig/node, sig/storage, alpha, v1.38; kep.yaml under `keps/sig-storage/`, feature gate `DynamicNodeLocalEphemeralVolumes`): opted in Sep 21, tracked Sep 23, **removed at Code Freeze Nov 17, 2026 12:05 UTC**, re-added Nov 21. k/k PRs listed in the issue description (the release team's tracking list): #143442 (closed, **not merged**), #143445 (merged Oct 27), #143474 (merged Nov 6), #143522 (merged Nov 4), **#143709 main implementation (opened Nov 2, merged Nov 20 23:28 UTC, after Code Freeze)**. **#143644** (merged Nov 6) mentions #6395 only in passing ("as discussed in") and is mainly KEP #1432 work: the test case for a passing mention that must stay `suggested`. Verified against the live API on 2026-11-21. The issue timeline has **no** cross-reference events, so PRs are found from the issue description and PR text, not the timeline.
  - Kubernetes v1.38: Enhancements Freeze Sep 30, 2026 12:00 UTC; Code Freeze Nov 17, 2026 12:00 UTC; release Dec 16, 2026.
  - Kubernetes enhancement **#2570** (long-lived KEP, history over 300 REST events): **removed at Code Freeze Nov 17, 2026 12:38 UTC**, re-added Nov 21 02:12 UTC. The REST events API misses this entirely; it is the regression fixture for the GraphQL timeline rule in section 7.
  - **KAFKA-19831**: links to KAFKA-17789; Fix Version changed 3 times in its history.
  - **KAFKA-21181**: status In Progress while tagged with released fix versions 4.0.0–4.3.0 (status drift + many-to-many releases).
  - New signals and modules add their own real fixtures (an AI-disclosed Kubernetes PR, a revert PR, a public meeting-notes excerpt) when they are built.

## 12. How to work in this repo

1. **Plan before coding.** For any task bigger than a small fix, write a short plan (files, steps, tests, risks, open questions) and wait for approval.
2. Work in **small, reviewable steps.** After each step: run `make test` and relevant evals; fix failures before moving on.
3. **Record design decisions** as ADRs in `docs/decisions/` (context, decision, alternatives, trade-offs). Explain every AI-vs-rules choice there.
4. Keep `README.md` current: problem, architecture diagram (all live sources), how to run, measured results with dates (including failures), limitations.
5. Never invent results. If a number is not measured yet, write "TBD (not yet measured)".
6. If real data looks different from what this file expects, stop and show the evidence before changing the design.
7. When unsure about a requirement, ask instead of guessing.
8. At the end of each step, summarize: what changed, how it was tested, what is next, and anything the owner must do by hand.
9. **Git and the pod:** follow AGENTS.md and docs/pod/RULES.md. One issue, one lane, one branch, one PR. Lanes: `harpreet` (`harpreet/`), `claude-agent` (`claude/`), `cursor-agent` (`cursor/`); Dependabot is a bot lane, never an agent lane. Every PR gets its lane label, exactly one `risk:low|medium|high`, and `needs-cross-review`; the other agent reviews with comments and switches it to `needs-human-review`; only Harpreet merges. Never push to main. Never commit secrets. Ask before deploying or applying Terraform.
10. **License:** the repo is open source under Apache-2.0 (`LICENSE` at the root).

## 13. Commands

```
make help                       # list all targets
make install                    # Python deps into .venv (uv)
make test                       # ruff + mypy + pytest
make test-integration           # needs the stack running
make web-test                   # eslint + tsc + vitest + next build
make up / make down             # local stack: Postgres, Redis, OTel Collector, Jaeger, API, worker, web
make migrate                    # alembic upgrade head
make backfill TEAM=kubernetes RELEASE=v1.38
make poll TEAM=kubernetes RELEASE=v1.38
make jira-sync                  # Kafka (Jira) sync
make evals / make evals-live    # offline evals / paid live agent evals
make sim-calibrate RELEASE=v1.38 / make sim-validate
make snapshot / make score-snapshots RELEASE=v1.39
make suggest-links RELEASE=v1.38
make tf-validate / make tf-plan
```

## 14. Simulator rules (Shadow-Org Simulator)

The simulator answers "what happens if we change something?" It must be credible enough for a leader to act on.

- **Calibrated on real data only.** Inputs come from measured distributions in the database: PR arrival rate per week, review rounds per PR, wait per review round, time to merge, reviewer workload (including unlinked PRs), interruption rate. Store each calibration with its source release range and date. With Jira: cycle time, throughput and sprint velocity per team.
- **Validate before use.** Replay a past release with its real staffing and check that simulated review waits and merge times match the actual ones (±20% on the median; record the result). If validation fails, the UI shows "not validated" and does not present what-ifs as reliable.
- **Model:** SimPy discrete-event simulation. Reviewers are resources; PRs are arrivals; review rounds are service time; interruptions remove reviewer capacity; new engineers ramp up over a configurable period. Output feeds the Monte Carlo forecast.
- **AI-era what-ifs:** PR volume multiplier (e.g. "AI doubles PR volume"), AI first-pass review (a configurable share of rounds handled before human review), PR size caps, and adding reviewers vs adding engineers. Each must be expressible with measured inputs, or it is labeled as an assumption.
- **Ranges, never single certainties.** Multiple seeded replications, shown as a range.
- **Baseline vs scenario,** side by side, with the difference highlighted.
- **Visible assumptions.** Every result lists the measured inputs and their source releases.
- **Scenarios are saved and comparable;** a "suggested fix" can be applied and re-run.
- **No AI in the numbers.** AI may describe a result in words; the fact checker verifies any claim about it.
- **Fast.** p95 under 2 seconds for a standard scenario.
- **Honest language.** Decision support ("if these assumptions hold, odds are likely X"), never guarantees.

## 15. Modules and plug-in rules

UI names (UX v1, locked in docs/ux/ux-v1-locked.md): Portfolio · Live Cockpit · Decision Studio · AI-native PDLC · Connect your tools. Sentence case everywhere except proper names (Program Intelligence Platform, Live Cockpit, Decision Studio, Shadow-Org Simulator).

| Module | What it does | Status (see README for measured results) |
|---|---|---|
| Live Cockpit | Plan vs real work, flags, dependencies, as-of replay (time machine) | Built |
| Forecast | Odds and merge dates per feature and release, backtested | Built, not validated |
| Decision Studio (Shadow-Org Simulator) | What-ifs on review capacity and staffing | Built, not validated |
| Stakeholder updates | Risk notes and VP update, fact-checked, TPM-approved | Built |
| Link review | AI link suggestions confirmed by a person | Built |
| AI-native PDLC | How the pod (people, AI agents, bots) builds, checks and ships; AI-era delivery signals (section 6) | Built for this repo (lab); pod facts next |
| Portfolio | All programs at once: stage, bottleneck, next decision, waiting on you | Next (UX v1) |
| RAID tracker | Risks, actions, issues, decisions from meetings and tickets | Planned |
| Release readiness | Go/no-go from real signals and configurable criteria | Planned |
| Retro insights | What slipped, why, and patterns across releases | Planned |

- **A module is done** when it has: data through the shared core, deterministic facts with tests, an ADR, AI (if any) behind the fact checker with an eval gate, a UI page, OTel spans, and a measured result in the README (or "TBD").
- **Connectors** declare what they provide (planning items, code activity, conversations, incidents) and are configured per team in `connectors/teams/<id>.yaml` today, and per tenant in the database once multi-tenancy exists. Adding a connector must not require changes to `engine/`, `pipeline/`, `verify/` or `api/`.
- **Tenants:** every stored row carries a tenant ID once a second tenant exists. Tenant data is deletable on request, and every admin action is audit-logged.
