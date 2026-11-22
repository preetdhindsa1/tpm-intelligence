# ADR-0012: Review simulator (SimPy) and its validation

- **Status:** in progress (Phase 2 M5). The model and validation are done; the simulator is
  **not validated**. Scenarios, API and page are not built yet, pending the owner's decision.
- **Date:** 2026-11-22

## Context

CLAUDE.md §14:
- The simulator must be calibrated on real data only.
- It must be validated by replaying a past release with its real staffing, within ±20% on
  the median.
- It must be shown as "not validated" when it fails.

The owner chose to validate on **both v1.37 and v1.38** (2026-11-22).

## Decision (model)

- **Pools.** Reviewers are a capacity pool per SIG. A PR's pool is its first `sig/*` label
  in sorted order. SIGs with fewer than 100 PRs in the source releases share `other`.
- **Counting reviewers.** Reviewers are only ever counted per pool-week, never named or
  ranked (§10). A person reviewing in two SIGs is split between them by their share of
  rounds in each.
- **PR paths.** Each simulated PR copies a real PR from the source releases: its review
  rounds (ADR-0006), the real wait before each round, whether it merged, and its final
  delay. 20–30% of merged Kubernetes PRs have no GitHub review at all (approval through
  `/lgtm` comments), and they skip the queue.
- **One review round** (`simulator/model.py`):
  1. a delay that blocks nobody: the real wait × a fitted scale, separate for first and
     later rounds;
  2. a queue for a reviewer;
  3. reviewer effort, an exponential with a fitted mean.
  - The visible wait is the sum of the three.
  - Interruptions slow effort by 1 / (1 − share).
  - New reviewers ramp up from 10% speed.
- **Fitting** (`simulator/replay.py`, source releases only, meaning those finished before
  the validated release started):
  - For each candidate effort, the per-pool scales are bisected so that the median first
    and later waits match.
  - The effort kept is the one that best follows each source release's median review wait.
- **Validation.** The held-out release is replayed with its real PR arrivals and its own
  staffing. Its median review wait and median time to merge are compared with the real
  values, both observed until the same horizon (release day, or the end of the data for
  v1.38). 8 seeded replications.

## Results (2026-11-22, `docs/results/sim-validation-20261122T125655Z.json`)

| Release | Fitted on | Median review wait: real → sim | Median time to merge: real → sim | Result |
|---|---|---|---|---|
| v1.37 | v1.33–v1.36 | 0.72 → 0.62 days (**−13%**) | 3.78 → 3.20 days (**−16%**) | pass |
| v1.38 | v1.33–v1.37 | 0.94 → 0.58 days (**−38%**) | 2.55 → 2.35 days (**−8%**) | **fail** |

**The simulator is not validated.**

The fitted reviewer effort sits at the floor of its range, about 30 minutes per round. The
earlier releases' differences in wait are best explained with reviewer capacity mattering
almost not at all. v1.38 had 56% more PRs (2,091 against 1,342) with about the same number
of active reviewers, and its real waits rose. A model whose capacity barely matters cannot
predict that.

### How the model was reached (disclosed, because each version was checked against the
held-out releases)

| Version | Change | v1.37 wait / merge | v1.38 wait / merge |
|---|---|---|---|
| 1 | Exponential reviewer time per round, one fitted mean per pool | +104% / −11% | +90% / +16% |
| 2 | Separate fitted time for later rounds (re-reviews are faster: 0.49 against 0.7–1.1 days) | −11% / −40% | +11% / −2% (pass) |
| 3 | Reviewer busy for a scaled copy of each real wait (keeps the long tail) | +91% / +4% | +63% / +15% |
| 4 | Short blocking effort (7 days ÷ 90th-percentile rounds per reviewer-week) plus non-blocking delay | +12% / −35% | +21% / +6% |
| 5 | Effort fitted to the source releases' median time to merge | −13% / −16% (pass) | −38% / −8% |
| **6 (kept)** | Effort fitted to follow the source releases' wait, release by release | −13% / −16% (pass) | −38% / −8% |

Versions 1, 3 and 4 had structural flaws. Version 1 treated re-reviews like first reviews.
Version 3 made a reviewer busy for whole calendar days. Version 4 used a fixed percentile
that was not fitted. No version passed both releases.

Version 6 was chosen **before** its result was known, as the most principled: every
parameter is fitted on source releases only. It was then kept whatever its result.
Choosing among versions by their held-out results would be tuning to the test.

## Why it fails, as far as the data shows

1. **Kubernetes approves through comments.** `/lgtm` and `/approve` are Prow comments, not
   GitHub reviews, and the collector does not fetch PR comments. So "review rounds" and
   "active reviewers" miss a large part of real reviewer work, and the staffing input is
   mismeasured.
2. **Pool assignment by first sorted SIG label** puts many multi-SIG PRs in
   `sig/api-machinery`. For example, #6395's main PR #143709 is node and storage work.
3. **The earlier releases vary little in load per reviewer**, so they barely show how waits
   respond to capacity. v1.38 is outside that range.

## Alternatives considered

- **A fitted queueing formula (M/M/c) instead of SimPy.** It is less flexible for ramp-up,
  interruptions and per-PR paths, and CLAUDE.md names SimPy.
- **Loosening the tolerance, or validating on v1.37 only.** Rejected: the owner chose both
  releases, and §14 says to record the result, not move the bar.

## Trade-offs and consequences

- Until validation passes, no what-if may be presented as reliable (§14).
- Fitting takes about 1 minute per release, so it is run offline (`make sim-validate`), not
  on each request.

## AI vs rules

No AI. Every number is measured, fitted on past releases, or simulated with fixed seeds.
