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
