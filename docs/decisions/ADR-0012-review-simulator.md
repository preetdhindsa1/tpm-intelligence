# ADR-0012: Review simulator (SimPy) and its validation

- **Status:** accepted (Phase 2 M5), shipped **not validated**. It failed both releases on
  review wait after comments were collected. The owner chose (2026-11-22) to ship scenarios
  with a visible "not validated" label rather than rework the model now.
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

## Re-run after collecting PR comments (2026-11-22, `docs/results/sim-validation-20261122T150430Z.json`)

The first suspected cause (below) was fixed in the data, not the model:
- The collector now fetches PR comments. `/lgtm` and `/approve` count as approvals; other
  comments by people other than the author count as review activity (ADR-0006 update).
- v1.33–v1.38 were backfilled again.
- Validation was run **once** with the model (version 6) unchanged, as the owner chose.

| Release | Fitted on | Median review wait: real → sim | Median time to merge: real → sim | Result |
|---|---|---|---|---|
| v1.37 | v1.33–v1.36 | 0.125 → 0.381 days (**+205%**) | 3.78 → 3.31 days (−12%) | **fail** |
| v1.38 | v1.33–v1.37 | 0.054 → 0.243 days (**+350%**) | 2.55 → 2.43 days (−5%) | **fail** |

**The simulator is still not validated; it is now further off on review wait.**

- Counting comments changed what a "review round" is. The real median wait dropped from
  about 0.7–0.9 days to 1–3 hours, because many rounds are now quick comment replies.
- Time to merge does not depend on how rounds are counted, and it passes on both releases.
- The simulated wait stays far above the real one, although the delay scales are fitted
  so that pooled median waits match on the source releases. Reviewer effort is again at
  the floor (0.02 days), and several fitted scales are near 1. So the error is probably
  not reviewer capacity. A likely place is a mismatch between how the fit groups waits
  (first or later round per pool) and the overall median used for validation, now that
  short and long rounds are mixed. This was **not** investigated or changed, because any
  change chosen after seeing the held-out result would be tuning to the test.

## Why the first run failed, as far as the data showed

1. **Kubernetes approves through comments** (since fixed in the data; see the re-run above). `/lgtm` and `/approve` are Prow comments, not
   GitHub reviews, and the collector does not fetch PR comments. So "review rounds" and
   "active reviewers" miss a large part of real reviewer work, and the staffing input is
   mismeasured.
2. **Pool assignment by first sorted SIG label** puts many multi-SIG PRs in
   `sig/api-machinery`. For example, #6395's main PR #143709 is node and storage work.
3. **The earlier releases vary little in load per reviewer**, so they barely show how waits
   respond to capacity. v1.38 is outside that range.

## Scenarios (shipped not validated, 2026-11-22)

The owner chose to ship what-ifs with a visible "not validated" label (§14 allows this) and
to move on, rather than rework the model now.

- **Calibration** (`make sim-calibrate RELEASE=v1.38`, `scripts/calibrate_simulator.py`):
  - fitted offline on the releases finished before the release started;
  - stored in `sim_calibrations` (migration 0006) with its source releases, date, fitted
    values, the measured inputs (real PR paths, no names or text) and the newest
    validation result;
  - requests never re-fit.
- **Starting state** (`simulator/scenario.py`):
  - the release's open PRs now, each at the review round it has reached;
  - the release's own measured reviewers per week per pool.
- **Horizon:** until the next milestone: Code Freeze, else release day, else 4 weeks.
- **What can change, per pool:**
  - experienced reviewers ±n;
  - new reviewers with a ramp-up;
  - share of time lost to interruptions.
  - Also, for the whole release, new PRs as a multiple of the measured rate.
- **Results:**
  - median review wait, PRs merged by the horizon, and PRs not merged;
  - per pool and in total, as the median and 10th–90th percentile of 8 seeded runs.
- **Baseline vs scenario:**
  - The baseline always runs alongside the scenario and is cached per calibration and
    data version.
  - Each PR's random numbers are drawn per pool and run, so a change to one pool leaves
    every other pool's results identical (common random numbers; tested).
- **Saved scenarios** (`sim_scenarios`): named per release, stored with their settings,
  result, calibration id and who saved them. Two can be compared side by side; the page
  warns when they used different calibrations.
- **Honest labels:**
  - Every API response carries `validated: false` and a note saying not to rely on it.
  - The page shows the validation errors in a banner.
  - Because the fitted reviewer time sits at its lower limit, the page also says that
    reviewer capacity has very little effect in this model. Removing 15 of 21 sig/node
    reviewers moves its median wait only from 0.39 to 0.41 days.
- **Speed** (measured 2026-11-22, local Docker, v1.38 with 756 open PRs, 40 different
  scenarios):
  - warm requests: median 0.70 s, **p95 0.86 s** (target under 2 s);
  - the first scenario after new data: 1.2 s (baseline not yet cached);
  - before the fix below, p95 was 3.9 s.
  - The fix: full garbage-collection passes, triggered by simulator requests, re-scanned
    the ~300k projected events, which caused 3–4 s pauses on every ~9th request. The API
    now calls `gc.freeze()` after building a release view.
  - The first call after an API restart waits about 42 s for the release view itself.
    That was already the case and is not simulator time.
- **Not done:**
  - Simulator output does not feed the feature odds: an unvalidated model must not change
    the forecast. Deferred to M7, and only if a model passes validation.
  - No AI description of results and no "suggested fix" yet.

## Alternatives considered

- **A fitted queueing formula (M/M/c) instead of SimPy.** It is less flexible for ramp-up,
  interruptions and per-PR paths, and CLAUDE.md names SimPy.
- **Loosening the tolerance, or validating on v1.37 only.** Rejected: the owner chose both
  releases, and §14 says to record the result, not move the bar.

## Trade-offs and consequences

- Until validation passes, no what-if may be presented as reliable (§14). The UI says so.
- Any future rework must be validated on a release not used to choose it. v1.37 and v1.38
  have now been seen.
- Fitting takes about 1 minute per release, so it is run offline (`make sim-validate`), not
  on each request.

## AI vs rules

No AI. Every number is measured, fitted on past releases, or simulated with fixed seeds.

## Addendum (2026-11-25, #97): why the review wait failed after comments were collected

**Evidence only. The model is unchanged. Each next step waits for the owner.**

### Finding: bot accounts were counted as human reviewers

`engine.review_rounds.is_bot()` recognizes logins that end in `[bot]`, `-bot` or `-robot`. GitHub's **GraphQL** API, which the poller uses, returns app accounts **without** the `[bot]` suffix. REST, which the webhook receiver uses, keeps it. Checked on 2026-11-25 on kubernetes/kubernetes#144449: REST `kubernetes-prow[bot]` (type `Bot`), GraphQL `kubernetes-prow` (`__typename: "Bot"`). So every bot comment the poller stored counts as a human review round.

Accounts making a PR's **first review round within 1 minute of its opening** (`scripts/diagnose_sim_wait.py` and an ad-hoc count, local data until 2026-11-22). Bots and tools only:

| Release | PRs with a review round | Instant first rounds | By account |
|---|---|---|---|
| v1.35 | 808 | 69 | `linux-foundation-easycla` 68 (CLA bot) |
| v1.36 | 1,211 | 147 | `linux-foundation-easycla` 147 |
| v1.37 | 1,304 | 762 | `kubernetes-prow` 602 (Prow bot, new for v1.37), `linux-foundation-easycla` 147, `copilot-pull-request-reviewer` 13 (AI reviewer) |
| v1.38 | 2,091 | 1,946 | `kubernetes-prow` 1,761, `linux-foundation-easycla` 178, `copilot-pull-request-reviewer` 7 |

In-sample (source releases only, the fit that validation uses for v1.38), the share of real waits under 1 minute is 3.7–4.4% for v1.33–v1.36 and **28%** for v1.37. 59% of v1.37's *first* rounds are under 1 minute, and its real first-round median is 0.0001 days. The simulated median stays near 0.26 days for every source release. The +205% and +350% errors of the second run came from this change in the data: Kubernetes' Prow started commenting from an app account in v1.37. They did not come from the model.

### Effect, measured once

`simulator.replay.validate` was run **once**, model unchanged, with only these three GraphQL bot accounts treated as bots (in memory; what the collector fix below will store):

| Release | Median review wait: real → sim | Median time to merge: real → sim | Result |
|---|---|---|---|
| v1.37 | 0.433 → 0.409 days (−5.5%) | 3.78 → 3.32 days (−12%) | **pass** |
| v1.38 | 0.615 → 0.361 days (**−41%**) | 2.55 → 2.67 days (+5%) | **fail** |

**The simulator is still not validated.** v1.38's remaining miss is the one from the first run: reviewer effort is fitted at its floor (0.02 days), so capacity barely matters, and v1.38 had 56% more PRs than the source releases with about the same reviewers.

### The proposed fixes, in order, each for the owner to approve

1. **Data (no model change).** The poller fetches `author { login __typename }` and stores a `Bot` login as `<login>[bot]`, the same as REST and webhooks. A bot flag joins the event identity, so a backfill re-stores the old records with the right login. Then backfill Kubernetes v1.33–v1.38 and Kafka, and re-run every measured result that reads review rounds: this validation, the forecast backtests, and time to first review in the lab. **This changes published numbers.** It is a correction (CLAUDE.md section 6: bot and AI-reviewer actions are never human review). `copilot-pull-request-reviewer` is an AI reviewer: excluded from human review now, and counted as AI review when the Wave 3 signals land.
2. **Model (v1.38 still fails).** Not changed and not tried. Options to choose from *before* any is run against the held-out releases:
   - (a) Estimate reviewer effort from measured capacity (review rounds per active reviewer-week at the busiest weeks of the source releases), instead of fitting it to waits that barely respond to load.
   - (b) Fit effort with v1.33–v1.37 as sources, and validate on v1.39 when it ships (the first release no fit has seen).
   - (c) Keep the model, and keep "not validated" on the page, with these numbers.
   Choosing among (a)–(c) by their v1.38 result would be tuning to the test, so the choice comes first.
