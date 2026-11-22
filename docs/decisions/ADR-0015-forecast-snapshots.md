# ADR-0015: Daily forecast snapshots and the first unseen test (v1.39)

- **Status:** accepted (Phase 2 M7 step 5)
- **Date:** 2026-11-22

## Context

Every forecast result so far is a backtest on v1.33-v1.38. Those releases were seen
while the model was chosen: required PRs (ADR-0005 variant 2), recalibration,
the validation rule, and main-PR merge times (M7 step 4). So no result is out-of-sample.
A fair test needs forecasts that were recorded **before** the outcome existed, and that
cannot be edited afterwards.

CLAUDE.md section 6 also asks for history as timestamped snapshots. Section 8 asks for AI
to run only when odds change meaningfully, which needs yesterday's odds.

## Decision

1. **Two append-only tables** (migration 0007):
   - `forecast_snapshot_runs`: one row per release, day and model version. It holds the
     settings, calibration inputs, validation labels, base rate and release curve.
   - `forecast_snapshots`: each feature's odds (and range, raw odds), merge-date
     forecast (status, done day, 10th/50th/90th, by freeze, by release day) and CDF.

   A Postgres trigger refuses every `UPDATE` and `DELETE` on both tables. A unique key
   allows one run per release, day and model version. A second attempt is ignored, never
   merged.
2. **Recorded automatically.** When the API computes a release view (boot warm-up, warmer,
   or a request), it stores that day's snapshot if it does not exist yet. Releases more than 14
   days past release day are not recorded. `make snapshot` does the same on demand.
3. **Model version** = `MODEL_NAME` plus a hash of every setting that changes the output.
   `MODEL_NAME` must be bumped whenever model code changes. Snapshots only count for the
   version that made them, so a changed model starts a new, separate test.
4. **Scoring** (`make score-snapshots RELEASE=v1.39`). It runs only after release day + 14
   days. It uses the snapshot closest to each lead time (within 2 days) and the same scores
   as the backtests: Brier skill against the recorded base rate for odds; coverage and CRPS
   skill against the earlier-release baseline for merge dates.

## Frozen for the v1.39 test (recorded before any v1.39 data exists)

- **Model version:** `forecast-m7.1+1a53f2d9`, code as of commit `80ce26a` plus this
  step (which adds recording only).
- **Settings:** 20 replications × 500 draws, seed 1338, 10th-90th interval, required
  PRs = main PR and its stated prerequisites, merge times from main PRs only, no
  non-code removal factor. Recalibration as in ADR-0005.
- **Odds pass if** Brier skill > 0 at 28, 14 and 7 days before v1.39's Code Freeze.
- **Merge dates pass if**, at 28, 14 and 7 days before Code Freeze and 3 days after,
  coverage of the 10th-90th range is 70-90% **and** CRPS skill > 0.
- A missing snapshot at a lead time counts as a failure for that lead time.
- The result is published whether it passes or not. If the model changes during
  v1.39, the frozen version is still scored. The new version is reported separately,
  marked as starting mid-release.

**Prerequisite:** v1.39's schedule is not published yet. Snapshots start once its dates
are added to `collectors/github_poller/release_calendar.yaml` and its data is collected.
Recording runs for whichever release is current; until v1.39 starts, v1.38 is recorded
(after its freeze, merge dates only).

## Alternatives

- **Re-run the model later "as of" each date.** This is what the backtest does, but the
  model and code can change in between, and it is easy to tune without noticing. Stored
  predictions cannot be re-tuned.
- **Store snapshots in the events table.** Events are source facts; forecasts are
  derived. Mixing them would make projections depend on model output.
- **Allow corrections.** Rejected: any edit makes the test unfalsifiable. A wrong snapshot
  stays, and the issue is written next to the score.

## Trade-offs

- About 70 rows per release per day: small.
- The trigger also blocks legitimate clean-up, such as dropping a test release. That needs a
  migration that disables the trigger, which leaves a trace in the repository.
- Recording depends on the API computing the view that day. With the warmer running
  this happens every 5 minutes. If the API is down all day, that day is missing, which is
  recorded as missing, never back-filled.
