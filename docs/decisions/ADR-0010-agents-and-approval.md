# ADR-0010: Risk analyst and VP summarizer agents, live evals, TPM approval

- **Status:** accepted. M3a (risk analyst) and M3b (VP summarizer and approval) are done.
- **Date:** 2026-11-22

## Context

M1 built the fact checker and M2 the AI gateway. M3 adds the first agents. The owner's
choices (2026-11-22):

- The approver is recorded as `APPROVER_NAME` (Harpreet), labelled "local,
  unauthenticated", until sign-in arrives in Phase 3.
- One retry when more than 30% of claims are removed.
- Executive updates of at most about 200 words, plain and factual.
- Risk notes generated **only when a feature page is opened**, never in the background.

## Decision (M3a)

1. **Fact selection is code** (`agents/selection.py`).
   - A feature is *at risk* if it is in the release and has a warning or critical flag,
     or its odds are below the base rate.
   - The agent sees only that feature's facts, its verified PRs, the release dates and
     its SIGs' unlinked load. No people appear in the facts.
2. **Flags carry their meaning as facts** (`verify/build.py`).
   - Each flag has `flag.<code>.severity` and `flag.<code>.message`, the rule's own
     sentence.
   - Live evals showed that without these the model called warnings "critical" and
     shortened "not merged *by* Code Freeze" to "not merged".
3. **Draft → verify → one redraft** as a LangGraph state machine (`agents/loop.py`).
   - If more than 30% of claims are removed, the model drafts once more, with the removal
     reasons as input.
   - The attempt with the most verified claims wins. Only verified claims are stored or
     shown.
4. **Risk analyst** (`agents/risk_analyst.py`, prompt `risk_analyst.v4`, `simple` model,
   effort `low`).
   - Generated on page open via `GET /releases/{r}/features/{n}/risk-note`.
   - Stored in `risk_notes` (migration 0003) and reused until the facts change
     meaningfully (ADR-0009) or the prompt changes.
   - If the budget blocks a call, the API serves the old note marked `stale`, or `paused`
     when there is none. It is non-essential.
5. **Two new fact-checker rules**, both found in live runs and backed by eval cases:
   - "before/after Code Freeze" must agree with the cited date (`relation_mismatch`).
   - Every calendar date written in the text must be the date of a cited fact.
   - Fact values are type-checked against their kind: a list of failing-check names had
     been stored as a "count".
6. **Live agent evals** (`make evals-live`, paid; `evals/agents.py`).
   - Cases: 12 real fact sheets from v1.37 and v1.38, 7 days before and 1 day after Code
     Freeze (`scripts/build_agent_cases.py`).
   - Deterministic metrics, with no AI grading AI:
     - Removal rate of the shown attempt ≤ 10%.
     - Every critical flag cited by a verified claim (100%).
     - Odds honesty: claims citing odds also cite `odds.validated` when it is false (100%).
     - 2–5 claims per note.
7. **CI gate without paid calls** (`evals/agent_gate.py`). CI requires a committed,
   passing results file for the *current* prompt SHA and default model. Any prompt or
   model change fails CI until `make evals-live` passes (CLAUDE.md §8).

## Results (live, Haiku 5.5, 12 cases, 2026-11-22; `docs/results/agent-evals-*.json`)

| Prompt | Removal rate | Critical coverage (min) | Odds honest | Cost | Gate | What reading the notes showed |
|---|---|---|---|---|---|---|
| v1 | 4.1% | 0.5 | yes | $0.019 | fail | Critical flags described but not cited; warnings called "critical"; raw decimals |
| v2 | 4.1% | 1.0 | yes | $0.022 | pass | "not merged" for "not merged by Code Freeze"; "removed … before Code Freeze" when it was after |
| v3 | 4.4% | 0.5 | yes | $0.023 | fail | "not merged by Code Freeze" said 7 days *before* freeze; a wrong date in the text |
| **v4** | **4.0%** | **1.0** | **yes** | **$0.024** | **pass** | No wrong statements found by the developer on reading all 12 notes. 2 claims correctly removed ("19 days" for 19.8; an uncited "0.7 days") |

v2 passed the automated gate but was rejected after reading the notes. The metrics catch
wrong values, missing citations and uncited numbers. They do not yet catch every wrong
*word*, so a human read of the notes stays part of the eval until a labelled semantic
check exists.

First real use through the API (#6395, 2026-11-22): 4 verified claims, 0 removed, matching
the history verified in CLAUDE.md. $0.0013, about 8 s; the second request reused the note
at $0.

## Decision (M3b)

1. **Asks come from rules, not AI** (`agents/asks.py`).
   - Each flag type maps to one fixed action. For example, `review_waiting` gives "Find a
     reviewer for #N", and `main_pr_not_merged` (still in the release) gives "Confirm the
     exception for #N, or remove the feature".
   - They are `feature:<key>::ask.<code>` facts. An "Asks" claim must cite one and repeat
     its exact text as its value, so the AI cannot invent actions such as "reallocate 3
     TPMs".
2. **Update facts** (`agents/selection.py`, `update_facts`): release counts, the 8
   highest-ranked at-risk features (most critical flags first, then most warnings, then
   lowest odds), up to 10 features removed at freeze, and the asks.
3. **VP summarizer** (`agents/vp_summary.py`, prompt `vp_summary.v1`, `summary` model
   Opus 5.5, effort `medium`, essential).
   - Output sections: Summary / At risk / Removed at Code Freeze / Asks. Only verified
     claims are kept, each in its own section.
   - Shown claims are capped at 220 words (owner: "at most about 200"). Claims past the
     cap are dropped and counted.
   - The header (release, dates, counts, "odds not validated") is computed by code.
4. **Approval workflow** (`exec_updates`, migration 0004; API
   `POST/GET/PATCH /releases/{r}/updates[/{id}]`, `.../approve`, `.../reject`):
   - `draft → approved | rejected`; only drafts can be edited or decided.
   - The TPM can remove or reword claims. Each edited claim is re-checked against the
     stored facts, and failures are shown as warnings.
   - Approving over warnings, or over a *stale* draft (facts changed meaningfully since
     drafting), needs an explicit acknowledgement. Both are recorded.
   - Decisions record `APPROVER_NAME` as "Harpreet (local, unauthenticated)" and the time.
   - **Nothing is sent.** An approved update offers "Copy as Markdown".
5. **Executive update page** (`/releases/{r}/update`): draft, choose a version, edit,
   approve or reject, and copy. Each claim shows ✓ and links to its sources. The removed
   count, model, prompt and cost are shown.
6. **Evals and gate.** `make evals-live SUITE=vp_summary` runs 4 real release fact sheets
   (v1.37 and v1.38, 7 days before and 1 day after freeze). Gate:
   - removal rate ≤ 10%
   - ≤ 220 words shown
   - the top 3 at-risk features each cited
   - every ask grounded in an `ask.*` fact
   - odds honesty
   - a non-empty summary

   The CI gate now covers both agents.

## Results (M3b, live, Opus 5.5, 4 cases, 2026-11-22)

| Prompt | Removal rate | Max words shown | Top-3 coverage | Asks grounded | Odds honest | Cost | Gate |
|---|---|---|---|---|---|---|---|
| `vp_summary.v1` | **0%** | 217 (one draft trimmed by 1 claim) | 100% | 100% | 100% | $0.54 (about $0.14 per draft) | pass |

On reading all 4 drafts, the developer found no wrong statements. Flags kept their meaning
("not merged by Code Freeze"), and asks were only rule-made actions.

First real draft through the API (v1.38, 2026-11-22): 197 words, 0 claims removed, $0.18,
27 s. It is stored as draft #1 and left for the TPM to approve.

## Alternatives considered

- **Background generation for every at-risk feature.** Notes would be ready on page load,
  but the owner chose on-demand. About 70% of features count as "at risk" 7 days before
  freeze, mostly because their odds are below the base rate, so background runs would also
  cost more.
- **An LLM judge for faithfulness.** That is AI grading AI on facts (§2.1). Deterministic
  checks plus a human read are used instead.
- **Rendering flag claims from templates instead of AI wording.** It would be safest, but
  explanations combine several facts. The flag `message` facts and the relation and date
  checks narrow the gap. Revisit if the semantic error rate stays above zero.

## Trade-offs and consequences

- **Wording isn't fully verifiable.** Adjectives and meaning ("at risk", "late") can't be
  checked, only values, dates, numbers and freeze relations. The UI labels notes
  "AI-written · every claim checked against the data" and links each claim to its
  sources.
- **The eval set is small** (12 cases, 2 releases). Thresholds are a starting point.
- **The at-risk rule is broad.** 53 of 70 v1.38 features count as at risk after freeze.
  Tightening it is a product decision, left for later.
- **A VP draft costs about $0.14–0.18** with Opus 5.5. That's affordable on demand under the
  $2/day cap. A live eval run (4 drafts plus 12 notes) costs about $0.57.

## AI vs rules

- **AI:** wording the explanation, choosing which 2–5 facts matter most.
- **Rules:** which features are at risk, what facts the agent sees, whether each claim is
  shown, when to regenerate, the budget, and every number.
