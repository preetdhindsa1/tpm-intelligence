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
- Bot detection is a login-suffix heuristic (`[bot]`, `-bot`, `-robot`). Prow acts through
  `k8s-ci-robot`, which posts many comments; the `-robot` suffix was added with comment
  collection (2026-11-22).

## Update 2026-11-22: conversation comments count (Phase 2 M5)

Kubernetes reviewers approve through Prow comments (`/lgtm`, `/approve`), not GitHub
reviews. In v1.33–v1.38, 20–30% of merged PRs had **no** GitHub review record, so rounds
built from reviews alone missed much of the reviewers' work. This was found when the
simulator failed validation (ADR-0012).

- The poller now reads each PR's conversation comments (`comments` in `PRFields`, with
  pagination). It stores a `pull_request.comment_posted` event with the comment's id,
  author, time and the Prow commands found at the start of a line (`lgtm`, `approve`,
  `hold`, and their cancels). **The comment text is not stored.**
- Review rounds group review records **and** comments by the same person (same 60-minute
  window). A comment with `/lgtm` or `/approve` counts as `approved`; any other comment by
  someone other than the author counts as `commented`.
- Comments by the PR author and by bots are excluded, as before.

Consequence: rule flags and forecast calibration that use rounds now see comment-only
reviews too. Their counts and waits change after the re-backfill.

## AI vs rules

Rules only: counting is a fact.
