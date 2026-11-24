# ADR-0020: This project tracks itself, on a calendar clear of the holidays (Phase 3 M5)

- **Status:** accepted (owner chose option B, 2026-11-23; dates set by the owner, 2026-11-23)
- **Date:** 2026-11-23

## Context

P3-M5 adds GitHub webhooks so events reach the dashboard in seconds (event -> dashboard
p95 < 30 s, CLAUDE.md section 9). GitHub only delivers webhooks from repositories where
the GitHub App is installed, which needs admin rights. We are not admins of
`kubernetes/kubernetes` or Apache's Jira, so Kubernetes and Kafka stay polled every
5 minutes. Measuring the webhook path needs a repository the owner controls, with a plan
(issues in a milestone) and code (PRs) in the shape the platform expects.

## Decision

**The platform tracks its own development** in `preetdhindsa1/tpm-intelligence`:

- `connectors/teams/tpm-intelligence.yaml`: plans are GitHub issues in a milestone named
  after the release (`Phase 3`); code is the PRs that close them (`Fixes #12`), matched by
  the `github_issue` link pack. Its own project key, `tpm-intelligence`, so it never mixes
  with Kubernetes or Kafka.
- It is real data, so it carries no sample-data banner.
- Webhooks from the GitHub App deliver events in seconds. The cloud poller also polls this
  project every 5 minutes as a reconciliation pass, in the same run as Kubernetes
  (`--poll TEAM=RELEASE`, repeatable). Both paths give the same event IDs, so a fact
  arriving both ways is stored once (P3-M5 step 2).

**Phase 3 calendar** (`connectors/teams/tpm-intelligence-calendar.yaml`, UTC):

| Milestone | Date |
|---|---|
| Cycle start | 2026-11-30 |
| Planning freeze (issues in `Phase 3` set) | 2026-12-14 12:00 |
| Code freeze | 2027-01-14 12:00 |
| Release | 2027-01-20 |

The first proposal (start Nov 22, code freeze Dec 14, release Dec 21) put the release
inside the year-end holiday season. The owner pointed out that real release calendars
avoid it. The dates above skip US Thanksgiving week and the holiday change moratorium
(about Dec 18 to Jan 4), and give ten working days after people return before code
freeze. The owner set the cycle start and planning freeze.

## Alternatives

| | A: separate demo repo | **B: this repo (chosen)** | C: skip webhooks |
|---|---|---|---|
| Data | invented, labelled "sample" | real | none |
| New repository | yes | no | no |
| Changes how we work | no | a PR per change with `Fixes #N` | no |
| Measures the 30 s target | yes, on demand (scripted activity) | yes, slower to collect | no |

- **A** gives activity on demand but the data is invented. "Measure, don't claim" fits
  real data better.
- **C** leaves the 30 s target unmeasured.
- **A second Cloud Run job per team** instead of `--poll` pairs would also need its own
  scheduler, IAM binding, alert and deploy step. One job polling teams in turn keeps one
  of each. A failing team does not stop the others, and the job's exit code still reports
  it to the existing alert.

## Trade-offs and limitations

- **Small sample.** One owner's PRs arrive slowly, so the webhook p95 will be measured on
  few events and labelled as a small sample.
- **Starts empty.** Nothing counts before the cycle start (Nov 30). Until the `Phase 3`
  milestone and its issues exist, the project shows no features.
- **Slower way of working.** Changes go through PRs that close issues, rather than direct
  pushes to `main`.
- **A longer poll run.** A Kubernetes poll took 74 s (p50) and at most 124 s over 24 runs
  (2026-11-23); this project adds seconds. Both must finish inside the 5-minute schedule.
- **Linking is rules only.** The deterministic `github_issue` pack verifies a closing
  keyword (`Fixes #12`) or a `Feature: #12` line; a bare `#12` elsewhere stays
  `suggested` until a person confirms it. No AI is involved in this decision.

## Results (P3-M5, measured 2026-11-24)

Webhook event -> live page, in the cloud, after the pipeline fixes of ADR-0022
(`scripts/measure_webhook_latency.py`, per-event method;
`docs/results/webhook-latency-cloud-20261124T044532Z.json`):

| | n | p50 | p95 | max |
|---|---|---|---|---|
| **GitHub event -> push to an open page** | 27 | 5.7 s | **9.7 s** | 12.2 s |
| GitHub -> receiver (GitHub's delivery) | 27 | 2.2 s | 6.1 s | 7.0 s |
| Receiver -> push (queue, store, recompute, send) | 27 | 3.6 s | 7.3 s | 7.6 s |

- **Passes the 30 s target** (CLAUDE.md section 9), with Kubernetes and Kafka polls and the
  hourly Jira sync running at the same time (window 04:29-04:45 UTC).
- Each webhook event is timed to the first push after it was stored, from the receiver,
  worker and API log lines. GitHub's timestamps are whole seconds on GitHub's clock, so
  figures are accurate to about +-1 s.
- Before the fixes, typical events were already 2-10 s, but some took 60 s to 14 minutes;
  ADR-0022 lists the five causes.
- **Small sample:** one owner's activity on one repository in one window, 3 short of the 30
  planned (published at the owner's request; the count keeps growing with activity).
- Pre-cycle PRs count: PRs opened before the 2026-11-30 cycle start link to Phase 3 features
  (webhooks deliver them; the poller only looks from the cycle start).
