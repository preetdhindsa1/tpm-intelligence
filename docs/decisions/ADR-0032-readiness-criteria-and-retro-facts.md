# ADR-0032: Readiness criteria and retro facts

- **Status:** accepted for the criteria (#181). The decision log, retro facts (#182) and
  backtest result (#184) are added as addenda when they are built.
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
