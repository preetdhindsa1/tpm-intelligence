# Roadmap

What each phase set out to do, what is done, and what is left. Updated as milestones close.
Last updated 2026-11-24 (pipeline fixes, hardening progress). Measured numbers live in the README's "Measured results" table;
this page only says where things stand.

**Legend:** ✅ done · 🟡 in progress or partly done · ⬜ not started · ❌ measured and failing

## Phase 1: collect, link, compute, show (done)

| Item | Status | Notes |
|---|---|---|
| GitHub poller (Kubernetes), normalized events, Postgres event log | ✅ | GraphQL timelines for issue history (CLAUDE.md section 7) |
| Linker (KEP keys, tracking lists, feature gates, labels) | ✅ | Coverage 68/69 tracked v1.38 features; precision per method not labelled yet |
| Engine: graph, critical path, rule flags, Monte Carlo odds | ✅ | ADR-0005 |
| API and web dashboard, local Docker | ✅ | |
| Forecast backtest | ❌ partly | Beats the base rate in 9 of 12 cases, not all: odds are shown as "not validated" |

## Phase 2: AI that only explains, simulate, approve (done)

| Item | Status | Notes |
|---|---|---|
| Claim model, fact checker, evals harness | ✅ | ADR-0008; labels pending TPM review |
| AI gateway: model routing, cache, daily budget cap, Langfuse | ✅ | ADR-0009 |
| Risk analyst and VP summarizer with TPM approval | ✅ | ADR-0010; removal rate 4.0% / 0% on live evals |
| AI link suggester with review queue | ✅ | ADR-0011; 104 suggestions await review |
| Shadow-org simulator (SimPy) | ❌ partly | ADR-0012. Built and calibrated, but **not validated**: median review wait misses the ±20% replay target (v1.37 +205%, v1.38 +350%); time to merge passes |
| Dashboard redesign, forecast improvements, merge dates | ✅ / ❌ | ADR-0013, ADR-0015. Merge-date forecasts are **not validated** (full rule passed in 2 of 12) |

## Phase 3: make it real (in progress)

Calendar (ADR-0020): cycle start 2026-11-30, planning freeze 2026-12-14, code freeze
2027-01-14, release 2027-01-20. Tracked in the `Phase 3` GitHub milestone.

| # | Milestone | Status | Notes |
|---|---|---|---|
| P3-M1 | Sign-in and permissions | ✅ | ADR-0016 |
| P3-M2 | Cloud deploy (live demo) | ✅ | ADR-0017; renamed URL in ADR-0021 |
| P3-M3 | Apache Kafka via Jira | 🟡 | ADR-0018. Collector, linking (81% of 4.4.0 features) and UI done. Jira plan synced hourly and `apache/kafka` PRs every 5 minutes in the cloud since 2026-11-24 (#47). **Left:** no freeze dates, so no Kafka odds (#8); components not mapped to teams |
| P3-M4 | Faster recompute | ✅ | ADR-0019 (link once, cache the calibration; incremental projection dropped after profiling). Cloud recompute p95 9.2 s |
| P3-M5 | Webhooks end to end | ✅ | ADR-0020 (this repo tracks itself; repository webhook), ADR-0022 (pipeline under real load). End-to-end timing live; five causes of slow events found and fixed (deploy overlap, short Pub/Sub pulls, one-event-at-a-time storing, skipped pushes, timing the wrong event). Measured p95 **9.7 s** (n = 27), passes the 30 s target. ✅ |
| P3-M6 | Operations | 🟡 | Alerts email the owner and fire on time (#14, #54); uptime checks, SLO dashboard, runbook, CI scanning, Kafka sync done. **Left:** see "Hardening" below (#7) |

Also done in Phase 3: rename to Program Intelligence Platform (ADR-0021); forecasts say
"not enough history" instead of a fake 50% (#9); poller fixes (#11).

## Hardening (part of P3-M6 unless noted)

| Item | Status |
|---|---|
| Alerts reach a person | ✅ email channel, tested 2026-11-24 |
| Uptime check and availability alert (SLO 99.5%) | ✅ (#36) |
| Billing budget alert | ⬜ |
| Fact-checker removal-rate and AI-spend-at-80% alerts (CLAUDE.md section 9) | ✅ (#45) |
| SLO dashboard (freshness, event to dashboard, simulator p95, availability, AI spend) | 🟡 live (#40); simulator p95 and AI spend not drawn yet |
| Runbook (deploy, Terraform apply, rollback, each alert) | ✅ `docs/runbook.md` (#38) |
| Event pipeline keeps up with polls and syncs (batched storing) | ✅ ADR-0022 (#50) |
| Backlog alert fires in minutes, not 18 | ✅ 3 min held for 2 (#54) |
| Cloud SQL backups | 🟡 configured; restore never tested |
| Scheduled Jira and Kafka PR sync in the cloud | ✅ hourly Jira job, Kafka PRs in the 5-minute poll (#47) |
| Dependency and secret scanning in CI | ✅ pip-audit, npm audit, gitleaks, Dependabot (#18, #34) |
| Security review of the public endpoints (sign-in, webhooks, API) | ✅ `docs/security-review.md` (#64); follow-ups #65, #66 |
| Load test of the API and live stream | ⬜ |

## Proof (results still to measure or pass)

| Result | Status | Needs |
|---|---|---|
| Event to dashboard via webhooks, p95 < 30 s | ✅ 9.7 s (n = 27, 2026-11-24) | More samples over time |
| Linking precision per method | ⬜ TBD | The owner labels `evals/cases/linking.csv` (70 rows) |
| Link suggester reviewed precision | ⬜ TBD | The owner reviews the 104 suggestions |
| Fact-checker labels | 🟡 | The owner's review |
| Simulator validation (±20% on replay medians) | ❌ | Model work on review waits |
| Simulator p95 < 2 s for a standard scenario | ⬜ not yet measured in the cloud | SLO dashboard |
| Forecast on an unseen release (v1.39, scored as it runs) | ⬜ | Time: v1.39 starts after v1.38 ships (2026-12-16) |
| Availability 99.5% | 🟡 uptime checks live since 2026-11-24 (#36); needs a month of data | Time |

## Not scheduled yet (from CLAUDE.md, no phase owns them)

To decide: a Phase 4, or recorded as out of scope.

- Jira comment summarizer agent (CLAUDE.md section 3).
- A sample Jira Cloud site with webhooks, and team cycle time, throughput and sprint
  velocity from Jira (sections 1, 14).
- Per-team data isolation, so users only see what they can see in the source system
  (section 10). Not needed while all data is public.
