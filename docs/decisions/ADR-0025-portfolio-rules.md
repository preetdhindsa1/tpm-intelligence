# ADR-0025: Portfolio rules

- **Status:** proposed (Wave 1, issue #92)
- **Date:** 2026-11-24

## Context

The Portfolio screen (UX v1, screen 2) shows every live program at once: its stage, its
scope, its biggest bottleneck, the next decision, what waits on a person, patterns across
programs, and the modules still to come. Leaders compare programs on this screen, so the
same facts must always give the same answer, and every number must trace back to stored
data. The contract is `docs/api/ux-v1-contract.md` (`GET /portfolio`).

The data already exists. Release calendars come from the team connectors. Flags, linked
PRs and outcomes come from the release view. Draft updates and link suggestions are
stored. Lane counts come from the lab report (ADR-0023). The Portfolio adds no new data
source. It only chooses and orders facts that other pages already show.

## Decision

All rules are deterministic code in `engine/portfolio.py` (pure functions, no I/O). All
times are UTC.

1. **Programs.** One row per team in `connectors/teams/` (not `_template`), for its
   current release: the earliest release not yet released, else the newest
   (`ReleaseService.current_release_name`, the same rule the app uses on boot). A team
   with no release, or whose release fails to compute, goes in `skipped` with the reason.
   Rows are sorted by release date, then key.

2. **Stage** from the calendar, with `now` = the program's `as_of`:

   | Stage | When |
   | --- | --- |
   | Plan | before cycle start |
   | Build | cycle start ≤ now < Code Freeze |
   | Freeze | Code Freeze ≤ now < release |
   | Launch | release ≤ now < release + 7 days |
   | Learn | release + 7 days ≤ now |

   A missing cycle start, Code Freeze or release date makes the stage `null` (shown as
   "Stage unknown"), rather than a guess. Earlier stages are `done`, later ones
   `upcoming`. The next milestone is the next date ahead of `now` among cycle start,
   Enhancements Freeze, Code Freeze, release and launch end. Days to it count UTC
   calendar dates.

3. **Scope.** Features in the release now, and features ever in it (removed ones
   included, CLAUDE.md section 6).

4. **Biggest bottleneck.** The first rule that fires, in this order:

   | Order | Kind | Fires when | Severity |
   | --- | --- | --- | --- |
   | 1 | `critical_flags` | at least one in-release feature has a critical flag | critical |
   | 2 | `review_gap` | the team has agent lanes, 5+ PRs merged, and under half had an approving review | warning |
   | 3 | `linking_gap` | stage is Build or later and an in-release feature has no linked PR | warning |
   | 4 | `unlinked_load` | open PRs not linked to any feature exist | info |
   | 5 | `none` | nothing above | info |

   `critical_flags` names the most common critical flag code among those features (ties
   broken by code name), so the detail says what to look at. The review-gap threshold of
   5 merged PRs follows pod rule R22. The order puts facts that put the release date at
   risk first, then the review step, then data gaps.

5. **Next decision.** The first item a person must act on for that program: a draft
   executive update (newest update is a draft), then pending AI link suggestions, then
   PRs with no lane (teams with agent lanes only). None of them: `null`. These are the
   approval steps the platform already has (CLAUDE.md section 2, rule 4).

6. **Waiting on you.** The same three kinds, across all programs, in that order, then by
   program order. A what-if is never listed, because nothing is waiting on it.

7. **Across programs.** Three fixed sentences, each shown only when its fact is above
   zero: features re-added after the freeze (`late_code`), merges without an approving
   review in a lab team (`review_gap`, same threshold as rule 4), and open PRs not linked
   to any feature (`unlinked_load`). The text is a template filled with numbers.

8. **Coming next.** RAID tracker, release readiness and retro insights, status
   `planned`, with no numbers until those modules exist.

## Alternatives considered

- **A weighted bottleneck score** across flags, review and linking. Not chosen: weights
  would be invented, and a reader could not see why one program ranks above another. A
  fixed order is easy to explain and to test.
- **The stage from the work, not the calendar** (for example "Freeze" once most code has
  merged). Not chosen for v1: the calendar is what the program has agreed to, and work
  signals already show up as flags. A team without a calendar shows "Stage unknown".
- **AI-written "Across programs" insights.** Not chosen: those are facts, so they come
  from code (CLAUDE.md section 2, rule 1). AI may explain them later, behind the fact
  checker.
- **Listing a suggested simulation in "Waiting on you"** (the design canvas does). Not
  chosen: nothing is waiting on a person, and the list would then mix approvals with
  suggestions.

## Trade-offs and consequences

- The review gap reads the lab report, which counts a review from a non-author account
  only. In this repository every agent and the owner post from the owner's account, so
  reviews are not visible to it yet (issue #94). Until that is fixed, "0 with an
  approving review" is what the stored data says, and the ADR-0023 addendum explains it.
- The Launch window of 7 days is a starting value, not a measured one. It moves to team
  config if a team needs a different window.
- The endpoint computes each current release's view. Those views are warmed on boot, so
  the cost is one view per team, as the existing pages already pay.
- What would make us revisit this: a second tenant (per-tenant program lists, ADR-0034),
  or RAID and readiness data that should outrank the rules in rule 4.

## AI vs rules

Every field is rules. No AI is called by `GET /portfolio`. The text fields are templates
filled with computed numbers, so there is nothing for the fact checker to remove.

## Addendum (2026-11-25): the third stage is Verify, and each team names its boundary

**Context.** The stage between Code Freeze and the release was called "Freeze". Teams that
ship continuously (trunk-based development, feature flags, many deploys a day) have no code
freeze, so the word ties the product to release trains. But the moment a freeze exists for,
deciding that changes are checked and ready, does not go away for AI-native teams. It is the
bottleneck the platform measures: agents write code at machine speed, people verify it at
human speed.

**Decision (owner, 2026-11-25).**
1. The stage is renamed **Verify**: Plan → Build → **Verify** → Launch → Learn. Its
   boundaries do not change: it runs from the release's `code_freeze` date to its release
   date. The API's stage name changes from `"freeze"` to `"verify"`
   (`GET /portfolio` `stage.current` and `stage.stages[].name`).
2. Each team names the date that starts Verify in its connector file,
   `code_freeze_label` (default `"Code Freeze"`). Kafka sets `"Feature Freeze"`, its own name
   for the date the engine treats as Code Freeze (ADR-0018). A continuous team can use
   "Release cut" or "Feature complete". The API returns it on every release and Portfolio
   row (`code_freeze_label`). The web app shows it wherever the date appears ("Feature Freeze
   passed 3 Feb", "Verifying · past Code Freeze (17 Nov)"), and the bottleneck text uses it
   ("25 features past Code Freeze with the main PR not merged").
3. Internal names stay: the `code_freeze` calendar field, the `removed_at_freeze` flag and
   outcome codes, and Kubernetes copy that names its real milestone ("removed at Code
   Freeze") are facts about that team's process, not the stage name.

**Alternatives.** "Stabilize" or "Harden" (read as bug-fixing only), "Cutoff" (still a
freeze), "Ready" (vague). Keeping "Freeze" with a footnote would leave the main word wrong
for continuous teams.

**Trade-offs.** `"verify"` is a breaking change to the Portfolio contract. The only client is
this repository's web app, which changes in the same PR. The Launch window and every other
ADR-0025 rule are unchanged.

## Addendum 2 (2026-11-25): the review gap counts human reviews

**Context.** Rule 4's review gap compared merged pull requests with GitHub *approvals*. In
this repository every PR, review and comment is posted from the owner's account, and GitHub
does not let an author approve their own PR. So the Portfolio said "0 of 78 had an
approving review", while the front page and AI-native PDLC page, which read the pod facts
(ADR-0023 addendum 2), said "19 of 74 merged PRs had a human review". The same repository
showed two different numbers.

**Decision.** When the team has pod facts, the review gap uses them: merged people PRs (bots
excluded) and how many had a human review or comment before merge. The detail and the
"Review is the new bottleneck" text say "with a human review". The threshold is unchanged (a
gap when fewer than half were reviewed, from at least 5 merged). A team without pod facts
keeps the approval count. The row's facts carry both (`approved_merged`, plus
`human_reviewed` and `reviewed_of`).

**Trade-off.** "Human review" includes a comment by the owner without the agent marker line
(the pod rule). That is how the PDLC page counts it, so the pages now agree.
