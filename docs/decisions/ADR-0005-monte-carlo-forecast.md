# ADR-0005: Monte Carlo forecast of landing by Code Freeze

- **Status:** accepted (results section updated with each measured backtest)
- **Date:** 2026-11-21

## Context

Leaders need "what are the odds this feature makes Code Freeze?" with an honest range.
CLAUDE.md requires deterministic statistics (§2.1), calibration on past releases with only
data dated before the prediction point (§6), ranges rather than certainties, fixed seeds,
and measured accuracy (§2.5).

The data available per feature at time `t`: its open and merged linked PRs (created and
merged times, review rounds, CI), its release membership history, and the same facts for
finished releases (v1.36, v1.37).

## Decision

`engine/forecast.py`, a Monte Carlo over the feature's work:

1. **Open PRs: empirical residual time to merge.** For an open PR of age `a`, draw a
   calibration PR that was still unmerged at age `a`, and use its remaining time. PRs that
   were closed without merging, or never merged, count as "never". No fitted distribution:
   the method is explainable in one sentence and cannot be more confident than the data.
2. **Dependencies.** A PR cannot finish before a PR it states it depends on.
3. **Work not opened yet.** `q` = measured share of earlier-release features that got a new
   linked PR between the same days-to-freeze point and Code Freeze, split by whether the
   feature already had PRs. With probability `q` a new PR opens uniformly before freeze and
   takes a full sampled duration. This covers #6395 on 2026-10-30, when its prework PRs had
   merged but the main PR (#143709) was not opened yet.
4. **Outcome.** Lands if all sampled completions are at or before Code Freeze. The backtest
   truth is "still in the release 3 days after Code Freeze" (the release team removes
   features at freeze; #6395 and #2570 were removed and later re-added, which counts as
   **not** landed by freeze).
5. **Range.** 20 bootstrap replications (resampled durations, `q` from its Beta posterior)
   × 500 draws. Report the mean and the 10th-90th percentile, e.g. "38%, likely 30-46%".
   Seeds are fixed per feature, so results are reproducible.
6. **No future data.** The world is projected from events before `t`; calibration uses only
   releases released before `t`. Text fields (PR bodies, issue descriptions, `kep.yaml`) are
   the latest version, a known approximation (README limitations).

7. **Recalibration** (`engine/recalibrate.py`, added 2026-11-21 after the first backtest).
   Raw odds are mapped to the landing rate actually observed on **earlier** releases. Each
   earlier release is forecast at the same lead time from its own past and scored against
   its outcome. The map is binned, shrunk toward the base rate (4 pseudo-observations per
   bin) and forced to be monotone (pool-adjacent-violators), so ranking is unchanged. Raw
   odds are kept and shown.
8. **Validation gate** (`api/validation.py`). Odds count as validated only if the newest
   backtest shows recalibrated skill > 0 at every lead time for every backtested release
   (tightened 2026-11-22; see results). Otherwise the API and dashboard
   label them "not validated" and show the base rate next to them (same rule as CLAUDE.md §14
   for the simulator).

Backtest (`engine/backtest.py`): at 28, 14 and 7 days before freeze, forecast every feature in
the release, then score with the **Brier score** against a **climatology baseline** (the
calibration releases' landing rate at the same lead time). Skill = 1 − Brier / Brier_baseline.

## Alternatives considered

- **Parametric survival model (Weibull / Cox) on PR features.** More statistical power per
  sample, but more assumptions to defend, and two releases of data is little to fit
  covariates on. Revisit once more releases are backfilled.
- **Feature-level classifier (e.g. logistic regression on flags).** Gives a number, but not a
  mechanism the simulator (phase 2) can perturb ("add a reviewer"). Monte Carlo over PRs
  plugs into SimPy directly.
- **Expert rules ("late main PR ⇒ 30%").** Not calibrated. Rejected.
- **AI estimates.** Forbidden for numbers (CLAUDE.md §2.1).

## Trade-offs and consequences

- Two calibration releases give a small sample: ranges will be wide, and rates in rare
  buckets fall back to the Beta(1, 1) prior.
- "Never merged" calibration PRs make the model pessimistic for very old open PRs: if no
  calibration PR survived to that age and then merged, the PR is modelled as never merging.
- Review queues and reviewer load are not modelled yet; the phase-2 simulator adds them.
- Outcome = membership 3 days after freeze. Features kept despite unmerged code, or removed
  for non-code reasons (docs, PRR), count against the model. The backtest measures that gap.

## Results (measured 2026-11-21; files in `docs/results/`)

Outcome = still in the release 3 days after Code Freeze. Baseline = calibration releases'
landing rate at the same lead time. Skill = 1 − Brier / Brier_baseline (> 0 beats the baseline).
AUC = how well the odds rank landed above slipped features (0.5 = random).

**Variant 1: all open linked PRs must merge** (`backtest-20261121T221345Z.json`)

| Release (calibrated on) | Lead | n | Landed | Brier | Baseline | Skill | AUC |
|---|---|---|---|---|---|---|---|
| v1.37 (v1.36) | 28 / 14 / 7 d | 89 / 91 / 91 | 77% | 0.50 / 0.57 / 0.58 | 0.18 / 0.19 / 0.19 | −1.83 / −1.91 / −1.99 | 0.66 / 0.63 / 0.65 |
| v1.38 (v1.36+v1.37) | 28 / 14 / 7 d | 86 / 87 / 87 | 72% | 0.53 / 0.54 / 0.53 | 0.20 / 0.21 / 0.21 | −1.65 / −1.57 / −1.52 | 0.53 / 0.60 / 0.68 |

Diagnosis: the assumption was false. At Code Freeze, 42% / 36% / 51% of the features that
**landed** in v1.36 / v1.37 / v1.38 still had a linked PR open. Their **main** PR was open for
only 19-24% of landed features, against 67-83% of slipped ones.

**Variant 2 (current default): only the main PR (and its stated prerequisites) must merge**
(`backtest-20261121T221421Z.json`)

| Release (calibrated on) | Lead | Brier | Baseline | Skill | AUC |
|---|---|---|---|---|---|
| v1.37 (v1.36) | 28 / 14 / 7 d | 0.31 / 0.33 / 0.37 | 0.18 / 0.19 / 0.19 | −0.78 / −0.69 / −0.92 | 0.65 / 0.65 / 0.68 |
| v1.38 (v1.36+v1.37) | 28 / 14 / 7 d | 0.32 / 0.36 / 0.35 | 0.20 / 0.21 / 0.21 | −0.60 / −0.71 / −0.68 | 0.60 / 0.63 / 0.63 |

**Verdict: the forecast does not yet beat the base rate.** It ranks features somewhat
(AUC 0.60-0.68) but is overconfident at both ends. Features given about 5-10% landed 60-70%
of the time. Features given 100% (main PR merged) landed about 80% of the time, because
features are also removed for non-code reasons.

**Caveat:** variant 2 was chosen after looking at v1.36-v1.38 outcomes, so its backtest is
not fully out-of-sample. v1.39 will be the first unseen test.

**Variant 2 + recalibration, v1.33-v1.38 backfilled** (`backtest-20261122T014032Z.json`,
measured 2026-11-22, 245 s on a laptop). Each release is recalibrated only on releases before
it (v1.33 has no earlier release, so it serves only as calibration data).

| Release (recalibrated on) | Landed | Recalibrated skill 28 / 14 / 7 d | Raw skill | AUC |
|---|---|---|---|---|
| v1.35 (v1.34) | 52-63% | **+0.07 / +0.10 / +0.25** | −0.15 / −0.11 / +0.15 | 0.65 / 0.67 / 0.76 |
| v1.36 (v1.34-v1.35) | 89-91% | +0.09 / **−0.15 / −0.29** | −0.10 / −1.27 / −1.42 | 0.69 / 0.51 / 0.64 |
| v1.37 (v1.34-v1.36) | 77% | +0.13 / +0.07 / **−0.01** | −0.39 / −0.69 / −1.00 | 0.64 / 0.66 / 0.65 |
| v1.38 (v1.34-v1.37) | 72% | +0.09 / +0.02 / +0.04 | −0.47 / −0.74 / −0.73 | 0.59 / 0.63 / 0.64 |

**Verdict: recalibration helps, but does not beat the base rate everywhere.** It improves on
the raw odds at every release and lead time. It beats the base rate in 9 of 12 cases, by small
margins (+0.02 to +0.25). It fails on v1.36 at 14 and 7 days: 91% of v1.36 features landed,
well above the earlier releases' rate, so the recalibration was too pessimistic. It also fails
narrowly on v1.37 at 7 days. Ranking stays modest (AUC 0.51-0.76).

**Validation gate tightened (2026-11-22, `api/validation.py`).** The old gate checked only the
newest release, and this run passed it on v1.38 alone. v1.38 was also used to choose
variant 2. The gate now requires skill > 0 at every lead time for **every** backtested
release, so the odds stay "not validated".

Next candidates (not done): non-code removals (features with the main PR merged still slip
about 20% of the time), per-stage new-PR rates, and v1.39 as the first unseen test.

## AI vs rules

No AI. Every number comes from measured data and this simulation.

## Merge dates (M7 step 2; validation rule fixed 2026-11-22, before any result was run)

**What.** `engine/merge_date.py` keeps the Monte Carlo draws (`simulate_completion`, a
refactor of `forecast_feature` that reproduces the existing odds exactly; checked on the
87 real v1.38 features 14 days before freeze). It reports *when* a feature's required
work (main PR, its stated prerequisites, a new PR if needed) merges, as days relative to
Code Freeze. It also works after Code Freeze, when the question is "by release day?". A
release curve sums the features' draws: how many features will have their required code
merged by each day, with a 10th-90th percentile range of that count.

**Truth.** The day the feature's main PR and its stated prerequisites merged, from all
data. Never merged = later than the horizon (release day + 14 days).

**Backtest.** Releases v1.35-v1.38. Forecasts made 28, 14 and 7 days before Code Freeze
and 3 days after it, using only data before that time and calibration from releases
finished by then. Features already done at that time are not scored.

- *Coverage*: the share of features whose actual merge day falls in the forecast's
  10th-90th percentile range (should be about 80%).
- *CRPS* (one-day steps over the curve's days) against a **baseline**: the merge days, relative
  to their own Code Freeze, of earlier finished releases' features that were not done at
  the same point. Skill = 1 - CRPS / CRPS_baseline.

**Validation rule (fixed before the first run).** Merge dates count as validated only if,
for **every** backtested release and every lead time, coverage is between 70% and 90%
**and** CRPS skill is above 0. Otherwise the API and UI label them "not validated", as for
the odds and the simulator.

### Merge dates: results (measured 2026-11-22)

**Two corrections to the backtest, made after its first run and before any change to the model.**
1. *Truth used PRs from later releases.* The "actual" main PR was the newest PR of all
   time, so for long-lived KEPs it was a PR from a later release cycle. Only 23-30% of
   v1.35-v1.37 features then counted as merged by the horizon, below what had already
   merged at freeze. Truth now uses only PRs opened before the release day.
2. *v1.38 cannot be scored yet.* Its horizon ends 2026-12-30 and the data ends
   2026-11-22, so open features counted as "never merged". It was wrongly included in
   the rule. The backtest now refuses releases whose horizon has not ended.

The first run's file is kept: `date-backtest-20261122T193020Z.json`. Dropping v1.38
removed three of the four passing cases, so neither correction makes passing easier.

**Result** (`date-backtest-20261122T193530Z.json`, v1.35-v1.37, 218 s):

| Release | Lead (days before freeze) | n | Coverage of 10-90% range | CRPS skill | Count at release day: forecast (range) / actual |
|---|---|---|---|---|---|
| v1.35 | 28 / 14 / 7 / -3 | 57 / 42 / 39 / 5 | 84% / 79% / 79% / 80% | +0.00 / −0.14 / −0.01 / +0.03 | 63 (59-67) / 60 · 58 (54-61) / 57 · 59 (55-63) / 57 · 47 (46-48) / 44 |
| v1.36 | 28 / 14 / 7 / -3 | 47 / 47 / 36 / 13 | 83% / 74% / **69%** / **62%** | −0.07 / −0.36 / −0.53 / −0.16 | 54 (50-58) / 63 · 52 (48-56) / 63 · 57 (53-60) / 63 · 64 (62-66) / 61 |
| v1.37 | 28 / 14 / 7 / -3 | 53 / 53 / 53 / 11 | 83% / 83% / 72% / 82% | −0.31 / −0.30 / −0.36 / **+0.25** | 57 (53-61) / 66 · 57 (53-61) / 67 · 56 (52-60) / 67 · 63 (61-65) / 57 |

**Verdict: not validated.** The ranges are about the right width (coverage 69-84% in 10 of
12 cases). But the forecasts do not beat the simple baseline before Code Freeze, and they are
**too pessimistic**: for v1.36 and v1.37 the actual count at release day (63-67) was
above the forecast range. After Code Freeze the model beats the baseline in 2 of 3
releases. The API and UI label merge dates "not validated".

Diagnosis and next candidates (not done): the pessimism matches the odds model's (PR
durations from all linked PRs, including slow and never-merged ones, applied to main
PRs). Candidates: durations from main PRs only, durations per stage, and blending with
the baseline before freeze.

**Known inconsistency.** Merge dates skip a main PR closed without merging (a closed PR
cannot deliver code; six v1.38 features had one and looked "done" at once). The odds
model keeps its backtested behaviour, which treats it as nothing left to merge. To be
reconciled when the odds model is next changed and re-backtested.

## Step 4 (M7): main-PR merge times and non-code removals (measured 2026-11-22)

**Variants and rule, fixed before running.**
- **A (previous):** residual merge times drawn from all linked PRs.
- **B:** drawn from **main PRs only**, the PRs that decide the outcome. Side PRs include
  slow and abandoned ones, the suspected cause of the merge-date pessimism.
- **C:** B, plus a measured per-stage rate of features removed even though their code
  merged by Code Freeze (docs, PRR, the release team's call), applied to the odds.

A variant is adopted only if it lowers the mean score (Brier for odds, CRPS for merge
dates) and is better than A in at least 8 of 12 cases. Every release has already been
seen, so any gain is **in-sample**. The validation rules are unchanged.

**Odds** (v1.35-v1.38 × 28/14/7 days; files `backtest-20261122T200418Z-A-all-durations.json`,
`...T200949Z-B-main-durations.json`, `...T200418Z-C-main-durations-noncode.json`):

| Variant | Mean Brier | Better than A | Skill > 0 | AUC range |
|---|---|---|---|---|
| A | 0.1897 | — | 9 of 12 | 0.51-0.76 |
| **B** | **0.1885** | **9 of 12** | 9 of 12 | 0.53-0.76 |
| C | 0.1955 | 3 of 12 | 7 of 12 | 0.60-0.78 |

**Merge dates** (v1.35-v1.37 × 28/14/7/-3; `date-backtest-20261122T200838Z-B-main-durations.json`
against `...T193530Z.json`): B's mean CRPS is 14.63 against 15.78, better in 8 of 12. Coverage
is 75-92%. The release-day count is no longer too low for v1.36/v1.37 (forecast 58-69,
actual 63-67), but v1.35 is now too high (forecast 63-67, actual 57-60). Skill > 0 in 3 of 12.

**Decision.**
- **B adopted** for both odds and merge dates (`ForecastConfig.durations = "main"`). The
  improvement is small and in-sample.
- **C rejected.** It ranks features better (AUC up in 11 of 12) but its probabilities
  are worse, so it fails the rule. The ranking signal may be worth adding as a
  recalibration input later, not as a multiplier.
- **Neither is validated.**
  - Odds still fail v1.36 at 14 and 7 days and v1.37 at 7 days.
  - Merge dates pass the full rule in 2 of 12 cases.
  - Both stay labelled.

`api/validation.py` now reads only backtests whose recorded settings match the deployed
model, so a variant's file cannot decide the label of another model.
