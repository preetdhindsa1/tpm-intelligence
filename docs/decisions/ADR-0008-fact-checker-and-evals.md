# ADR-0008: Fact checker and eval harness

- **Status:** accepted
- **Date:** 2026-11-22

## Context

Phase 2 adds AI agents that explain engine facts. CLAUDE.md requires the following:

- Agents receive only engine facts (§8).
- Agents return structured claims (§2.3).
- Every claim is verified before anyone sees it, and unverifiable claims are removed and
  counted (§2.3, §8).
- Prompt or model changes must pass `evals/` before merge (§8).

The verifier comes first (M1), so no AI output can reach a person without passing it.

## Decision

1. **Fact sheet** (`verify/facts.py`, `verify/build.py`).
   - Engine output becomes typed facts with stable keys:
     - `release::code_freeze_at`
     - `feature:<key>::odds.probability`
     - `pr:<key>::merged_at`
     - `sig:<sig>::unlinked_open_prs`
   - Kinds: `count`, `probability`, `date`, `duration_days`, `boolean`, `label`.
   - Only verified links become PR facts. Suggested links appear only as a count.
   - Odds carry `odds.validated`, so a summary cannot call unvalidated odds reliable.
   - The fact sheet is the agent's **whole input**.
2. **Claim** (`verify/claims.py`, Pydantic).
   - Fields: `text`, `type`, `refs` (fact keys, primary first) and `value`.
   - Agents produce one atomic claim per checkable statement.
3. **Checker** (`verify/checker.py`, pure). Each claim gets one verdict, checked in order:
   - `removed: no_supporting_data` if there are no refs, a ref is unknown, or there is no
     value.
   - `removed: type_mismatch` if the claim's type differs from the primary fact's kind.
   - `removed: wrong_value` if the value doesn't match the primary fact within the
     tolerance for its kind:
     - counts: exact
     - probabilities: ±1 percentage point, and must be 0–1
     - durations: ±0.5 day
     - dates: ±60 s, or the same UTC day for a date-only value; naive times are rejected
     - labels: case-insensitive
   - `removed: text_mismatch` if the sentence states a number that no cited fact supports.
     Dates, times, versions and issue/PR/Jira keys are masked first.
   - Otherwise `verified`. Counts per reason and the removal rate are kept for publishing.
4. **Evals** (`evals/`, `python -m evals.run_evals`, `make evals`, a CI step).
   - **Fact-checker suite.** 36 labelled claim cases, using real-shaped facts from #6395,
     #2570, v1.38, KAFKA-21181 and KAFKA-19831. It covers every verdict, including the
     claims from the dashboard mockup ("reallocating 3 TPMs reduces risk by 45%",
     "92% confidence of a bottleneck"), which have no facts behind them. The checker is
     deterministic, so the threshold is 100% agreement.
   - **Linking suite.** Precision per method and status on a stratified, seeded sample of
     real v1.38 links (`scripts/sample_link_cases.py` → `evals/cases/linking.csv`,
     70 rows). It reports "TBD (not yet labelled)" until a TPM labels the rows, and has
     no threshold until a baseline exists.
   - Results are saved to `docs/results/evals-*.json`. Agent suites
     (hallucination rate, faithfulness) join in M3.

## Alternatives considered

- **An LLM judge that checks claims.** It is non-deterministic, so it can't be the gate
  for facts (§2.1). It may later grade *wording* quality, but never values.
- **Free-text summaries checked by regex afterwards.** Brittle, and there is no way to know
  which fact a sentence relies on. Structured claims with refs make every check explicit.
- **Matching text numbers by exact string.** Fails on rounding ("38%" for 0.384). The
  tolerances by kind are documented and tested.

## Trade-offs and consequences

- **Judgement claims are removed** if they carry no checkable value ("#6395 is the riskiest
  feature"). Agents must ground judgements in a fact, such as a flag or the odds.
  Explanations will be terser, and that is intended.
- **Numbers written as words** ("three PRs") are not caught by the text check. Prompts will
  require digits, and the M3 evals will measure how often this happens.
- **The labels start as `proposed`,** written by the developer. They become `reviewed` only
  after a TPM checks them, and the eval output reports the split.
- **Kafka facts are illustrative.** They are hand-entered from the verified CLAUDE.md
  examples, because the Jira collector is Phase 3.

## AI vs rules

No AI here. This is the deterministic gate that every AI output must pass.
