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
   backtest shows recalibrated skill > 0 at every lead time. Otherwise the API and dashboard
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

**Variant 2 + recalibration, with v1.33-v1.38 backfilled:** TBD (not yet measured).

## AI vs rules

No AI. Every number comes from measured data and this simulation.
