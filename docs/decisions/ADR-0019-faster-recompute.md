# ADR-0019: Faster recompute: link once, cache the calibration (Phase 3 M4)

- **Status:** accepted (owner approved the plan and option A, 2026-11-23)
- **Date:** 2026-11-23

## Context

Every new event made the API recompute the whole release view. On real Kubernetes v1.38
data (294,328 events) that took **26.8 s on a laptop and about 56 s on the cloud API**
(1 vCPU). Pages never waited (stale-while-revalidate, ADR-0002 addendum), but new data
took up to a minute to show, against an event -> dashboard p95 target of 30 s
(CLAUDE.md section 9).

Profile of one recompute (`scripts/profile_recompute.py`, laptop, single run):

| Stage | s |
|---|---|
| Calibration on the 5 finished releases | 15.4 |
| Assess (includes its own linking) | 3.4 |
| Merge dates (includes its own linking) | 3.2 |
| Linking the release | 2.9 |
| Forecast (includes its own linking) | 2.9 |
| Projecting the world | 1.1 |

The plan originally included an incremental projection. The profile showed projection
costs about 1 s, so that idea was dropped: it would add risk of wrong numbers for almost
no gain.

## Decision

1. **Link once per recompute.** `assess_release`, `forecast_release` and
   `forecast_release_dates` take an optional `links`; the service links the release
   once and shares it. A test checks the assessment, odds and merge dates are identical
   with and without sharing (fixtures, fixed seeds, before and after Code Freeze).
2. **Cache the calibration (owner's option A, refined).** `calibrate_tracked` returns
   the subjects calibration read: the finished releases, every feature ever in them and
   every PR verified-linked to those features. The service reuses the calibration until
   a new event could change it:
   - reviews, comments and CI results never can (calibration does not read them);
   - a re-observed PR snapshot only if its created, merged or closed time, title or body
     changed (GitHub re-reports a PR on any activity);
   - any other event on a subject it read does;
   - and always after 6 hours, when the set of finished releases changes, or after a
     person's action (`invalidate`).

   The first version rebuilt on any event touching a subject it read. That reused the
   cache almost never: KEPs span releases, so 34% of the 20,000 most recent comment
   events hit the read set. The refinement was measured before it was adopted.

## Alternatives

- **Option B, time limit only (6 h).** Simplest and fastest, but any late fact on an old
  release (a PR merging late) would be up to 6 hours stale. Not chosen by the owner.
- **Option C, no cache.** Exact, but only saves the linking (~5 s).
- **Calibrate each finished release as of its own end** (release day plus the landed
  window). That would make the cache exact forever, but it changes the model's inputs,
  so the backtests would have to be re-run and re-validated. Possible later.

## Trade-offs

- **The one known gap:** a brand-new PR that links to an old feature is not a subject the
  calibration read, so it waits for the 6-hour limit. The forecast itself is unaffected:
  it reads the current release, which is recomputed on every event.
- The cache errs towards rebuilding: unknown event types and any change on a read subject
  rebuild it.
- Memory: the cached calibration is lists of durations and rates. Peak memory of the
  profile run was unchanged (1.09 GiB before and after).

## Results (measured 2026-11-23)

Laptop, real v1.38, recompute after one new event (a PR comment), single runs:

| | Before | Step 2 (link once) | Step 3 (cache) |
|---|---|---|---|
| After one new event | 26.8 s | 21.8 s | **4.6 s** |
| Cold start | 37.0 s | 31.7 s | 23.5 s |

Cloud and event -> dashboard p95: **TBD (being measured)**.
