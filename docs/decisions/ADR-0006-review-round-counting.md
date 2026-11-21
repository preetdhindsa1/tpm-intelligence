# ADR-0006: Count review rounds, not raw review records

- **Status:** accepted
- **Date:** 2026-11-21

## Context

GitHub stores one review record per "Submit review" action. Review effort and waiting time
feed the rule flags (M5) and the forecast calibration (M6), so the unit matters.

Real data (v1.38 backfill, 2026-11-21): the main #6395 PR, **#143709**, has **97 review
records**. Counted as rounds they would suggest 97 back-and-forth cycles. Many are one
reviewer submitting several comments minutes apart, plus the PR author replying to threads
(GitHub records those replies as `COMMENTED` reviews by the author).

## Decision

`engine/review_rounds.py`:

1. Drop records by the **PR author** and by **bots** (logins ending `[bot]` or `-bot`).
2. Group the rest **per reviewer**. A new round starts when the gap since that reviewer's
   previous record exceeds **60 minutes** (`RuleConfig.review_round_window`).
3. A round's **outcome** is its last decisive state (`approved`, `changes_requested`,
   `dismissed`), else `commented`.
4. **Wait before a round** = time from PR creation (first round) or the end of the previous
   round to this round's start, never negative. This is the queue time the forecast calibrates on.

On #143709 (as of 2026-11-21): **97 records → 10 rounds**. #6395's other PRs: 19 → 3,
10 → 3, 2 → 1.

## Alternatives considered

- **Raw records.** Inflates effort and wait counts by an order of magnitude for thorough
  reviewers. Rejected (CLAUDE.md §6).
- **One round per reviewer per PR.** Loses real iterations (review → changes → re-review),
  which is the signal we need.
- **Rounds split by new commits pushed.** Closer to "iteration", but needs commit history
  per PR (more API cost). Revisit if the 60-minute window proves wrong.
- **Per-day grouping.** Merges morning and evening sessions that really are separate rounds.

## Trade-offs and consequences

- The 60-minute window is a **starting value, not a measured optimum**. Sensitivity of the
  forecast to the window is TBD (not yet measured; M6 backtest).
- Rounds are per reviewer and used only in aggregate (per PR, per feature, per SIG queue).
  The platform does not rank or report individual reviewers (CLAUDE.md §10).
- Bot detection is a login-suffix heuristic. Prow acts through `k8s-ci-robot`, which does not
  submit reviews, so this has not mattered so far.

## AI vs rules

Rules only: counting is a fact.
