# ADR-0004: Linking confidence model (PR → work item)

- **Status:** accepted
- **Date:** 2026-11-21

## Context

A feature's odds depend on which PRs belong to it. A wrong link adds or hides remaining
work, so linking changes the facts. CLAUDE.md §2 therefore requires deterministic rules, a
method and confidence on every link, and `suggested` status for anything a rule cannot
verify.

What the live data showed (2026-11-21, #6395 and its PRs):

- **No cross-reference events.** The #6395 timeline has none, via REST or GraphQL, although
  every PR links the issue in its body. Timeline cross-references cannot be the discovery source.
- **The issue description is the release team's tracking list.** The Enhancements team asks
  owners to list "all PRs to the Kubernetes repo that are related to your enhancement" in it.
  #6395 lists #143442 (closed, not merged), #143445, #143474, #143522 and #143709.
- **PR authors declare the KEP in structured places:** a `KEP:` line (#143522, #143709), an
  "Implements … KEP-6395" phrase (#143709), or a bare URL under the PR template heading
  "Which issue(s) this PR is related to" (#143442, #143445, #143474).
- **Passing mentions exist.** #143644 is KEP-1432 work that mentions #6395 only "as discussed in".
  Counting it would add a PR to #6395 that its owners did not track.

## Decision

Deterministic rules in `linker/` (pure, mypy-strict), applied per PR:

| Method | Rule | Status | Confidence |
|---|---|---|---|
| `explicit_key` | KEP number in the PR **title**, on a **`KEP:` line**, in an **"implements … KEP-N"** phrase, or under the **"Which issue(s) this PR is related to"** heading | verified | 0.95 |
| `tracking_issue_link` | PR URL listed in the KEP issue description | verified | 0.90 |
| `feature_gate` | a gate name from exactly one KEP's `kep.yaml`, as a whole word in the PR title or body | verified | 0.75 |
| `explicit_key` | any other KEP mention (passing) | **suggested** | 0.50 |
| `feature_gate` | gate name shared by several KEPs | **suggested** | 0.40 |
| `labels` | SIG overlap | never creates a link; stored as `sig_overlap` evidence | n/a |
| `ai_suggested` | Phase 2 M4 (ADR-0011) | suggested (0.30) until a person confirms it (verified, 0.85; DB-enforced) | n/a |

- HTML comments are stripped first: the PR template has example text inside them.
- A reference only links to KEPs in the release being analysed.
- All candidates are stored with their evidence (location, text snippet, gate name). For
  counting, the strongest per (PR, work item) is used: verified beats suggested, then method
  rank (CLAUDE.md §6 order).
- Confidence values are **ordinal labels for the rule that fired, not measured
  probabilities**. Measured precision per method is TBD (not yet measured): it needs a
  hand-labelled sample.

**Approval note:** the "Which issue(s) this PR is related to" location was added during M4
after the approved rule list (title, `KEP:` line, "implements", tracking list). The real PRs
#143442, #143445 and #143474 use it. They are verified by `tracking_issue_link` anyway, so
the addition changes the method recorded for them, not their status.

## Alternatives considered

- **Count any mention.** Simple, but #143644 would count toward #6395 and inflate its
  remaining work. Rejected.
- **Only the tracking list.** Highest precision, but it depends on owners keeping the
  description current. Mid-cycle PRs are often added late. We keep explicit keys too.
- **AI linking now.** Out of scope for phase 1. When added, AI links stay `suggested`
  (enforced by a database CHECK).
- **Timeline cross-references.** Not present in the data.
- **SIG labels as a link source.** Each SIG has dozens of KEPs per release, so labels
  cannot identify one. Kept only as supporting evidence.

## Trade-offs and consequences

- Some real implementation PRs will appear only as `suggested` (passing mention, not in the
  tracking list). The dashboard must show suggested links so a TPM can confirm them.
- Phrase-based rules ("implements") are English-specific and can be gamed. Measuring
  precision on a labelled sample is required before quoting accuracy.
- Gate-name matching is limited to PR text: we never read diffs (CLAUDE.md §10).

## AI vs rules

Rules only. Linking changes the facts, so AI may only suggest (CLAUDE.md §2.2).
