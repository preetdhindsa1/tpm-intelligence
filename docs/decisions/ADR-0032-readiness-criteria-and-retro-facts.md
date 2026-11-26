# ADR-0032: Readiness criteria and retro facts

- **Status:** accepted. Criteria (#181), decision log (addendum 1), retro facts (#182,
  addendum 2), the v1.37 worked example (#183, addendum 3) and the backtest (#184,
  addendum 4). The backtest **failed**, so readiness is "not validated".
- **Date:** 2026-11-26

## Context

Wave 5 adds release readiness: a go/no-go view from real signals, and a person makes the
call. AI never computes a fact (principle 1), so every criterion is a rule over stored
data; until it is backtested it is "not validated" (principle 5). The API contract
(docs/api/readiness-retro-contract.md) came first, so the page is built in parallel.

## Decision

### Criteria (modules/readiness/rules.py)

Each criterion is `pass`, `fail` or `unknown` and carries its evidence (feature, PR or
RAID ID). `unknown` means there is no data to decide, never a guess. Only features in
the release at the as-of time count, so a feature removed at the freeze no longer
blocks it. Each team picks its criteria in `connectors/teams/<id>.yaml` (`readiness:`);
all five apply by default.

| Criterion | Fails when | Unknown when |
|---|---|---|
| `code_merged` | A feature's main PR is not merged by the freeze and has no exception evidence (re-added after the freeze, engine/freeze.py) | No features, or some features have no verified PR and none fails |
| `no_critical_flags` | A critical rule flag is open (table below) | Never |
| `ci_green` | An open linked PR has a failing check on its latest commit. Any failing check counts, because Prow does not mark required checks (CLAUDE.md §7); the detail text says so | No linked PRs |
| `risks_owned` | An open or in-progress *confirmed* RAID risk has no owner | No confirmed risks yet. Suggested risks never count, but the detail says how many wait for review |
| `docs_merged` | A linked PR in one of the team's `docs_repos` is not merged | No docs repo is configured, or none of its PRs are linked |

A critical flag stays open until its resolution holds:

| Flag | Resolved when |
|---|---|
| `main_pr_not_merged` | The same main PR merged later with exception evidence |
| `removed_at_freeze` | The feature is back in the release |

**Verdict:** `not_ready` when any criterion fails, `ready` when all pass, otherwise
`unknown`. Each criterion keeps at most 25 evidence rows, and `count` always holds the
full number.

**Kubernetes docs:** feature docs PRs live in kubernetes/website, which the platform does
not collect yet. So `docs_repos` is empty and `docs_merged` is `unknown` for Kubernetes,
which the page shows. CLAUDE.md §7: if data is missing, ship without it and say so.

### Backtest pass rule (#184), fixed before any result

The rule is fixed now so the result cannot shape it.

- **Replay:** run the criteria as of Code Freeze and as of release day, using only data
  available then. Releases: Kubernetes v1.36, v1.37 and v1.38 (if released), and Kafka
  4.4.0.
- **Per-feature prediction:** a feature is *flagged* at the freeze when `code_merged`
  fails for it or it has an open critical flag.
- **Outcome:** the feature *slipped* if it was removed from the release after the freeze
  or merged after the freeze. For Kubernetes, kubernetes/sig-release `exceptions.yaml` is
  the record of real exceptions where it exists.
- **Pass:** the freeze replay passes when all three hold:
  1. At least 60% of slipped features were flagged (recall ≥ 0.60).
  2. Flagged features slipped at least 15 points more often than all features did
     (precision ≥ base rate + 0.15). The base rate is the share of all features that
     slipped, which is what predicting at random would give.
  3. On release day, at most 5% of features that shipped fail a criterion (false no-go).
- Releases with under 20 features are reported but do not count toward the pass. If it
  fails, `validated` stays `false` ("not validated"); `GET /results` publishes it either way.

## Alternatives and trade-offs

- **An AI go/no-go call:** rejected. The verdict changes what ships, so it is a rule and a
  person decides (principle 2).
- **A release-level backtest:** rejected as the pass rule. Four releases are too few, and
  some feature is always unmerged at a Kubernetes Code Freeze; features give dozens of
  cases per release.
- **"No data" as pass:** rejected; a missing docs source would read as "docs merged".
- Exception evidence is re-adding after the freeze. The sig-release exceptions file is a
  better signal; it is the backtest's outcome record first, and joins the live rules only
  if the backtest supports it. `ci_green` over-counts optional checks, and says so.

## Addendum 1: decision log and the API on real data (#181, 2026-11-26)

- **Decision log** (`readiness_decisions`, migration 0011). A go/no-go call needs sign-in
  on the approver allowlist (ADR-0016) and a note of 3+ characters. Each row stores:
  - the decision and the note;
  - the time;
  - `facts_as_of`, the time of the readiness facts the person saw;
  - `verdict`, what the rules said then;
  - the login, for audit only. The API returns the role `approver`.

  A database trigger refuses UPDATE and DELETE, as for the event log and forecast
  snapshots.
- **API:** when a database is configured, `GET /readiness?release=` runs the team's
  criteria on the current release view and the RAID store. Each response has
  `synthetic: false`. A GitHub feature or PR in the evidence links to its page.
  - If the RAID store can't be read, `risks_owned` is `unknown` ("RAID items could not be
    read"), never a pass. A RAID outage must not read as "no risks".
  - Without a database, the synthetic fixture remains.
- **AI summary:** optional, and not built yet; `summary` is `null`. When it is built, it
  uses only these criteria's facts, and the fact checker checks each sentence.
- **Validation:** `validated` stays `false` until the backtest (#184) passes the rule
  above.

## Addendum 2: retro facts (#182, 2026-11-26)

- **Replay, not today's data.** `modules/retro/facts.py` projects the stored events as
  of noon UTC each day, from Enhancements Freeze to the outcome cutoff, and runs the rule
  flags. A day's warning uses only what was known that day. The replay leaves out
  confirmed link suggestions, which were decided later. Forecast snapshots (ADR-0015)
  begin in November 2026, too late for past releases, so the retro replays rule flags
  instead of reading stored odds.
- **Planned features** were in the release at Enhancements Freeze, or were added before
  the cutoff.
- **Slips** are judged at the forecast's outcome cutoff (`engine/forecast.py`):
  - `dropped`: out of the release at the cutoff, and in no later release;
  - `moved`: out of it, but in a later release of the same project (`moved_to`);
  - `late_exception`: landed, but its main PR merged after the freeze with exception
    evidence; or out at the cutoff and re-added later. #6395 in v1.38 is the second kind:
    removed Nov 17, re-added Nov 21.

  Kafka main PRs merged after Feature Freeze with no exception evidence aren't counted as
  slips. Kafka has no such signal (addendum 1).
- **First warning:** the first replay day before the slip with one of these warning
  flags: `late_main_pr`, `review_waiting`, `ci_failing`, `main_pr_not_merged`,
  `merged_after_freeze`, `removed_at_freeze`.
  - `no_linked_prs` is left out. Early in a cycle almost every feature has no PR yet, so
    it would warn about everything on day one.
  - `warned_landed` counts the features that landed but were warned before Code Freeze:
    the false alarms.
    Without it, a rule that warns about everything would look perfect on lead time.
- **Said vs showed:** each meeting's RAID items, suggested ones included with their
  review state, next to the replay day on or just before the meeting: features in the
  release, features at risk, and open critical flags.
- **Patterns:** grouped per pool, the feature's owning SIG (one pool per feature), across
  every stored release of the project. There are two:
  - `slipped`: the share of planned features that slipped;
  - `late_main_pr`: the share whose main PR opened within 21 days of the freeze.

  Pools with fewer than 10 features are counted in `suppressed_groups` but not shown.
- **Storage:** a replay takes minutes, so `python -m modules.retro.job --release KEY`
  computes the retro and appends it to `retro_runs` (migration 0012; a trigger refuses
  changes). The API serves the latest run, and returns 404 until one exists.
- **This repo's UX v1 sprint retro, per lane,** comes from PR data (`engine/lab.py`). It
  is a separate step.

## Addendum 3: worked example, the Kubernetes v1.37 retro (#183, 2026-11-26)

**Source.** The public v1.37 Release Retrospective is a Google Doc. It is linked from
`kubernetes/sig-release/releases/release-1.37/links.md`, and its plain-text export
returned HTTP 200 (22,010 bytes) without signing in on 2026-11-26.
- It's listed in `connectors/teams/kubernetes.yaml` with `layout: retro`. The collector
  stores it as one meeting dated by "Part 1: 29th Jul 2026".
- The meeting starts at "(+) What went well", so the call details and attendee list are
  dropped.
- The API labels it "Kubernetes v1.37, public retro" and links the doc.

**Masking found two gaps, both fixed before anything was stored:**
- A SIG lead was named by first name. No release-team list includes them, so
  kubernetes/community `sigs.yaml` (SIG chairs and leads) is now a people source.
- A v1.38 item kept a surname used on its own. Masking now also covers a listed
  person's surname as a separate word.

Re-running the leak check after the fixes, with 619 public names, finds 0 names in the
129 v1.38 items and 0 in the v1.37 items. The only hits were the ordinary words "Slack"
and "via".

**Items (suggested).** 10 items: 3 actions, 3 issues, 3 questions and 1 decision. None
had an owner or a KEP number. Cost: $0.0018. Three extraction runs gave 12, 13 and 10
items: the extractor isn't deterministic on this document, and a person confirms what
stays.

**Computed facts (replay, local database).**

| | v1.37 |
|---|---|
| Planned features | 98 |
| Slips | 32: 16 moved to a later release, 12 dropped, 4 late exceptions |
| Removed at Code Freeze (Jul 23 to 24) | 17 |
| Warned before the slip | 21 of 32. Median lead 35.2 days, mean 28.1 |
| First warning | `review_waiting` 15, `ci_failing` 5, `late_main_pr` 1, none 11 |
| Warned but landed (false alarms) | 47 of 66 |
| On the retro's date (replay day Jul 26) | 70 in the release, 36 at risk, 26 open critical flags |

**Where the retro and the data agree:**
- "Some KEPs had partial code merged then removed from milestone at Code Freeze": the
  replay shows 17 features removed at Code Freeze and 26 open critical flags at the
  cutoff.
- "Gather exception request data": the replay counts 4 late exceptions.

**Where they disagree, or one side is silent:**
- The replay's most common first warning is a review wait (15 of 21). The retro doesn't
  mention reviews.
- The warnings are noisy: 47 of the 66 features that landed were also warned. The
  `review_waiting` threshold (7 days) is the main cause, and lead times of 35 days mean
  many warnings fired on the first replay day. Lead time on its own overstates the
  warnings; the #184 backtest pass rule (precision against the base rate) is the honest
  test.
- "Multiple KEP owners unresponsive" has no signal in the platform's data. It measures
  PRs and reviews, not replies to comments or DMs.
- The docs, comms and process items have no counterpart in delivery data: handbooks, the
  PRR Freeze name, docs labels, dashboard monitoring, the release-notes milestone.
- The retro names no KEP numbers, so matching retro items to slips by explicit link
  finds 0 pairs. The comparison above is by topic, written by a person (this ADR), not
  computed.

## Addendum 4: readiness backtest result: **failed, not validated** (#184, 2026-11-26)

Run with `python -m modules.readiness.backtest_job`, on the rule fixed above before any
result. The result file is
`docs/results/readiness-backtest-20261126T084416Z.json`, also served by `GET /results`.

| Release | Features at freeze | Slipped (base rate) | Flagged | Flagged and slipped | Shipped on release day | False no-go |
|---|---|---|---|---|---|---|
| Kubernetes v1.36 | 78 | 34 (0.44) | 26 | 17 | 70 | 21 |
| Kubernetes v1.37 | 86 | 44 (0.51) | 29 | 25 | 20 | 4 |
| Kubernetes v1.38 | 86 | 30 (0.35) | 36 | 25 | not shipped yet | n/a |
| Kafka 4.4.0 | 20 | 10 (0.50) | 3 | 3 | 19 | 3 |
| **Pooled** | 270 | 118 (0.437) | 94 | 70 | 109 | 28 |

| Rule | Measured | Needed | Result |
|---|---|---|---|
| Recall | 0.593 | ≥ 0.60 | **fail** (just under) |
| Precision | 0.745 | ≥ base rate 0.437 + 0.15 = 0.587 | pass |
| False no-go on release day | 0.257 | ≤ 0.05 | **fail** |

So `validated` stays `false`. `/readiness` now reads this from the newest result file
instead of a fixed string, and shows the reason.

**Why the false no-go is high.** On release day, the features that shipped but were
flagged nearly all fail on the engine's *main PR* choice:

| Release | Main PR still open | Main PR closed unmerged | Merged after the freeze, no exception evidence |
|---|---|---|---|
| v1.36 | 13 | 7 | 1 |
| v1.37 | 3 | 1 | 0 |
| Kafka 4.4.0 | 0 | 0 | 3 |

The main PR is the most recently opened verified PR (engine/rules.py). For a shipped
feature, that is often follow-up work still open, or an abandoned PR. The Kafka cases
are the known gap: there is no exception signal after Feature Freeze (addendum 1).
Readiness is only as good as the main-PR choice. Fixing that choice, preferring a merged
implementation PR over a later open or closed one, is the next step. It needs its own
change, and the backtest must be re-run after it. It is not tuned here.

**Caveats.**
- "Shipped on release day" counts features whose milestone was still the release. For
  v1.37, many enhancement issues had moved to the v1.38 milestone by Aug 26, which leaves
  20. The false no-go rate is measured on those.
- The kubernetes/sig-release `exceptions.yaml` file exists for v1.36 only among these
  releases. It lists 4 Enhancements Freeze exceptions (2 approved, 2 rejected) and no
  Code Freeze exceptions, so it adds nothing to the Code Freeze outcome. Older releases
  (v1.33, v1.34) list Code Freeze exceptions and could check the exception-evidence
  signal later; they are not part of this rule.
