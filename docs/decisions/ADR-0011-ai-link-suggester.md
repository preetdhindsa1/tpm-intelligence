# ADR-0011: AI link suggester and the link review queue

- **Status:** accepted (Phase 2 M4)
- **Date:** 2026-11-22

## Context

Rules link 609 of the 2,757 PRs in the v1.38 window. The rules are KEP keys, tracking
lists and feature gates (ADR-0004). The rest count as reviewer load but explain no
feature. CLAUDE.md §2.2 allows AI to *suggest* links here, but an AI link must stay
`suggested` until a rule or a person confirms it. The owner approved the M4 plan on
2026-11-22.

## Decision

1. **Code builds the choices** (`linker/candidates.py`, pure).
   - For each unlinked PR, the release's features are ranked by word overlap. Rarer words
     weigh more, and a shared SIG adds a bonus.
   - Feature words come from the title, the KEP's one-line description, the KEP folder
     name and the feature gates split at capitals.
   - PR words come from the title (counted twice) and the body, without HTML comments,
     URLs or template headings.
   - The top 12 become the shortlist. A PR whose shortlist is empty gets no AI call.
2. **The AI picks or says none** (`agents/link_suggester.py`, prompt `link_suggester.v1`,
   `simple` model Haiku 5.5, effort `low`, non-essential).
   - The model sees only the PR text and the shortlist.
   - It returns a feature key or `null`, plus two quotes: one from the PR and one from the
     feature.
   - The prompt makes `null` the normal answer when in doubt, because a wrong link
     changes a forecast and a missing one does not.
3. **Code checks every answer** (`linker/suggestions.py`, pure).
   - The feature must be on the shortlist.
   - The PR quote must appear word for word (ignoring case and spacing) in the text the
     model was shown, and contain a meaningful word.
   - The feature quote must appear in that feature's title, summary or gate names.
   - Failures are stored as `dropped` and never shown as links.
4. **People decide** (`link_suggestions`, migration 0005; `agents/link_store.py`;
   API `GET /releases/{r}/link-suggestions`, `POST .../{id}/confirm`, `.../reject`; page
   `/releases/{r}/links`).
   - Only `suggested` rows can be decided, and decisions are final.
   - *(Since ADR-0016: `user:<github-login>` of a signed-in approver.)* Each decision records `user:<APPROVER_NAME> (local, unauthenticated)`, the time and an
     optional note. The database requires a decider on every decision.
5. **Engine merge** (`World.extra_links`, `engine.links.merge_extra_links`, pure):
   - A confirmed link becomes `verified` (method `ai_suggested`, confidence 0.85,
     `verified_by` the person) and counts like a rule link.
   - A pending suggestion is `suggested` (confidence 0.30) and never counts.
   - A rejection removes a suggested link for that pair, including a rule-made one such as
     #143644's passing mention.
   - A rule-verified link is never changed.
   - After each decision the API recomputes the release view, so facts and odds update.
6. **Batch job** (`agents/link_job.py`, `make suggest-links RELEASE=v1.38 [LIMIT=]`).
   - Open PRs go first, then the newest.
   - PRs already processed with the same input and prompt are skipped.
   - The run stops when the budget slows or pauses it, and the next run continues where
     it stopped.
7. **Evals without hand labels** (`scripts/build_link_cases.py`, `evals/link_suggester.py`,
   `make evals-live SUITE=link_suggester`).
   - Cases are PRs that rules linked to exactly one feature, with their KEP references
     and gate names removed. That gives known answers:
     - **positive:** the linked feature is on the shortlist; the right answer is that
       feature.
     - **negative:** it was taken off the shortlist; the right answer is `null`, and any
       pick is a false link.
   - Gate:
     - precision ≥ 0.80
     - false links on negatives ≤ 20%
     - dropped ≤ 15% of non-null answers
     - recall ≥ 0.40, so that answering `null` to everything cannot pass
     - no errors
   - CI requires a passing results file for the current prompt and model (ADR-0010).
8. **Precision on real PRs comes from the queue.** The person's decisions are the labels:
   confirmed ÷ (confirmed + rejected).

## Results (2026-11-22)

**Shortlist recall** (no AI; every rule-linked PR with its keys hidden,
`scripts/measure_shortlist.py`, `docs/results/shortlist-recall-*.json`):

| Release | Linked PRs | Right feature at rank 1 | In the top 8 | In the top 12 (used) | In the top 16 |
|---|---|---|---|---|---|
| v1.37 | 1,040 | 55.6% | 85.4% | **88.1%** | 89.3% |
| v1.38 | 949 | 51.5% | 83.5% | **86.8%** | 88.0% |

12 was chosen because each extra candidate costs about 60 tokens and recall levels off.

**Hidden-key live eval** (60 cases: v1.37 and v1.38, 40 positive and 20 negative; Haiku 5.5,
`link_suggester.v1`):

| Precision | Recall (positives) | False links (negatives) | Dropped | Cost | Gate |
|---|---|---|---|---|---|
| **84.8%** (28 of 33 shown) | 70% | 20% (4 of 20) | 5.7% | $0.025 | pass |

What reading the misses showed:
- **Both drops were right.** One answer had an empty quote; the other reworded the PR
  text instead of copying it.
- **All 4 false links went to a closely related KEP**, because the right one was off the
  shortlist. Examples: "PLR instrumentation" went to a different Pod Level Resources KEP;
  a gang-scheduling field went to Gang Scheduling instead of the Workload API KEP.
- **The 1 wrong pick was a plain error:** "Measure allocation per request" went to
  Weighted Load Balancing.

The prompt was not tuned against these 60 cases, to avoid fitting the test set.

**First real run** (v1.38, `docs/results/link-suggester-run-20261122-v1.38.json`):

| Item | Result |
|---|---|
| Unlinked PRs | 1,797 |
| No shortlist (no AI call) | 46 |
| Answered "none" | 1,636 |
| Suggested (waiting for review) | **104** |
| Dropped by checks | 11 |
| Cost | **$0.54** (about $0.0003 per PR) |
| Time | 8 minutes, 4 workers |

Reviewed precision: **TBD (not yet reviewed)**.

## Alternatives considered

- **Give the AI every feature in the release (106).** That costs about 8 times the tokens
  per call, and the shortlist check is what stops invented keys. 87–88% shortlist recall
  bounds what the AI can find, and that bound is measured.
- **Embeddings for the shortlist.** Possibly better recall, but it would add a model,
  a vector store and a second paid API. Word overlap is free, explainable and measured.
  Revisit if reviewed precision is fine but recall is too low.
- **Letting the AI confirm its own links when confident.** That breaks §2.2: AI only
  suggests.
- **An LLM judge to grade suggestions.** AI grading AI on facts (§2.1). Hidden-key cases
  and the person's decisions are used instead.
- **A separate labelling CSV for AI suggestions.** The review queue already records yes or
  no with a person and a time. Those decisions are the labels.

## Trade-offs and consequences

- **Recall is limited by the shortlist** (about 12–13% of linked PRs would miss) and by the
  model's caution (70% on positives). Unlinked PRs that stay unlinked still count as load.
- **The hidden-key cases are harder than real life in one way and easier in another.**
  Removing the key also removes the strongest words. But the PRs come from features that
  rules could link, which may not be typical of truly unlinked PRs. Reviewed precision on
  real suggestions is the number that matters.
- **Rejected pairs are never suggested again**, but a different feature can still be
  suggested for the same PR.
- **The suggester only looks at PRs with no link at all.** PRs with a rule-made
  `suggested` link already wait for a person; confirming them from the queue is a
  follow-up.
- **Feature-detail pages count confirmed AI links as PRs.** The link method stays visible
  as `ai_suggested` with the person who verified it.

## AI vs rules

- **AI:** reading messy PR text and choosing one of the candidates, or none.
- **Rules:** which PRs are looked at, which features are offered, whether an answer is
  kept, what confidence it has, and the budget.
- **Person:** whether the link is real. Nothing counts until a person confirms it.
