# ADR-0023: Multi-agent development lab

- **Status:** accepted
- **Date:** 2026-11-23

## Context

Changes were merged on a laptop and pushed straight to `main`. With no pull requests there is no review queue to measure. The platform's job is to measure review bottlenecks, so this repository has to produce them.

GitHub's contributor list on this date is `preetdhindsa1`, `claude`, and `dependabot[bot]`. The `claude` login is a commit attribution. `dependabot[bot]` is Dependabot. Neither login is a lane.

The ruleset **Multi-agent PR Review** is active on the default branch. A pull request is required, force-push is blocked, and the six CI jobs are required. Required approvals is 0, so the owner can merge a pull request they opened. The lab counts the owner's review comments plus the merge as the review.

## Decision

Three tool lanes, on this repository only, with the owner's consent. They are tools, not people.

Match order is label, then branch prefix, then trailer. First configured lane wins.

| Lane | Label | Branch prefix | Trailer |
|---|---|---|---|
| claude | `claude-agent` | `claude/` | `Co-Authored-By: Claude` |
| cursor | `cursor-agent` | `cursor/` | `Co-authored-by: Cursor Agent` |
| human | `harpreet` | `harpreet/` | none |

Trailers lose to the label and the branch. Agents copy `Co-authored-by` lines they see in `git log`. The Cursor lane stays `cursor-agent`. `dependabot/` branches and the `dependabot[bot]` login are not mapped to it.

A collision is two open pull requests whose stored paths intersect, or a pull request GitHub marks as conflicting with its base. Empty file lists do not overlap. Paths and line counts are stored. Patches and file contents are not.

The lab page shows counts from pull requests already opened in this repository: arrivals, the review queue, time to first review, rounds, rework, CI failures, and collisions. Below 20 merged pull requests the page says the sample is small and does not show a what-if comparison. The three what-ifs replay those pull requests (cap open agent pull requests, describe an automated first pass without inventing a second median, count splits if a line cap had applied). They do not call the Kubernetes review simulator and they do not change any forecast.

`AGENTS.md` is the rule file every coding agent follows. `CLAUDE.md` points at it.

## Alternatives considered

- Required approving review count of 1, with a machine account opening agent pull requests. Not chosen. The ruleset requires 0 approvals, which lets the owner merge their own pull requests. A machine account is not part of this change.
- Classify the lane from the GitHub contributor login. Not chosen. The `claude` login is an attribution, and `dependabot[bot]` is not Cursor.
- Put the what-ifs inside `simulator/scenario.py`. Not chosen. That model is SIG pools, it is not validated (ADR-0012), and these knobs must not move Kubernetes odds.

## Trade-offs and consequences

The review the lab measures is the owner's comments and the merge, because GitHub is not requiring a separate approval. That is less like a second person reviewing, and it is what the ruleset actually enforces.

File lists are capped at 100 paths. A truncated list is marked, and a known shared path is still a collision.

Webhook deliveries do not include the file list. The branch is recorded immediately. Paths arrive on the next poll. Mergeability is skipped when GitHub sends null.

What would make us revisit this: a required approval from an account that is not the pull request author, or enough merged pull requests that a what-if comparison is worth showing.

## AI vs rules

Lane classification, collisions, and every number on the lab page are deterministic code. AI is not asked who wrote a pull request or what the odds are. An agent may open the pull request. It does not compute the facts (CLAUDE.md section 2).

## Addendum 1 (2026-11-24, #108): who wrote a review

**Evidence.** On 2026-11-24 all 47 non-bot pull requests in this repository were opened from the owner's GitHub account, and so was every review and comment. The agents post with the owner's token (Dependabot is the only other author). `engine/review_rounds.activity()` drops activity by the PR author, so the lab counted no review at all in this repository. That included the owner's comments, which this ADR says should count. A login cannot tell an agent from the owner here.

**Decision (owner, 2026-11-24).** Every agent review or comment starts with a marker line `<Kind> · <lane label>`, for example `Cross-review · claude-agent` or `Reply · cursor-agent`. The poller and the webhook receiver read the first non-empty line (bold or code marks allowed) and keep only a tag such as `cross-review:claude-agent`. The text is never stored, as with Prow commands. The separator must be `·`, so ordinary first lines ("LGTM - thanks") never match. When a marker is present it is part of the event identity: a review stored before markers were read is stored once more with its tag. Events without a marker keep their old ids. The projection keeps a tag whichever copy arrives first. The tag changes nothing in review rounds or calibration: the pod facts (#94) read it.

**Limits.** An agent that forgets the marker is counted as the owner. A person could type a marker by hand. Both are visible in the PR thread, so a reviewer can catch them. Separate machine accounts per agent would remove both limits. They were not chosen now because they need accounts and tokens the owner does not have yet.

## Addendum 2 (2026-11-25, #94): pod facts on `GET /lab`

**Decision.** `GET /lab` gains `pod` for teams with agent lanes: the 4 members, the 7-stage pod flow, metrics against starting targets, and 8 pod rules checked against real PRs. Contract: `docs/api/ux-v1-contract.md`. Code: `engine/pod.py` (pure). The owner chose the whole history as the window, the same as the rest of the lab here. PRs from before the pod rules (PR #91, 2026-11-24) therefore show as breaking them. That is what happened, and the page says the rules started on that date.

**Rules, each defined before it was computed:**
- *Review actions:* a `cross-review:<agent label>` marker counts as that agent's review. An unmarked review or comment from a non-bot counts as human. Other agent markers (`reply:…`) are not reviews. Rounds group one actor's actions within 60 minutes (as `engine.review_rounds`).
- *Cross-reviewed:* a merged agent PR with a review by the other agent lane before merge (R13). *Human-reviewed:* a merged PR with a human action before merge. *R2:* a merged PR with no review from outside its own lane.
- *R8:* additions + deletions over 400 without the `size:exception` label. *R6:* not exactly one `risk:` label. *R9:* agent PRs opened while their lane already had 2 open. *R12:* no lane. *R26:* Dependabot PRs closed unmerged.
- *Kept (R21):* a merged PR is kept if no merged `Revert "…"` PR names it (`Reverts owner/repo#N`, GitHub's default) within the window. It is counted only once the merge is 30 days old; before that it is `not_measured` with the first eligible date.
- *Not measured, with the reason shown:* contract-first (R5: issues are not collected); first-pass approval (GitHub does not let a PR's author approve it, and every PR here is opened from the owner's account); human review load; three red CI runs (R17: only the latest commit's checks are stored).
- *Nothing to check is not "held":* a rule or stage with no PRs is `not_measured`. Medians need 5 merged PRs in the lane (R22).

**First measurement (2026-11-25, 68 PRs, 53 merged):** 6 of 38 merged agent PRs cross-reviewed. 11 of 52 merged PRs had a human action before merge. 12 of 13 Dependabot PRs closed unmerged. 48 of 55 PRs without exactly one risk tier. Median 11 minutes from open to merge.

**Limits.** An agent reply without a marker counts as human review (seen on #106). Review depth counts actions, not what was read.

## Addendum 3 (2026-11-25): the owner's merge is a person's approval

**Context.** The owner reported that the AI-native PDLC page undercounts human approval:
every PR here is approved by the human who merges it, but the page only counted written
reviews ("19 of 80"), and rule R2 called most agent PRs "approved alone". The platform
never stored who merged a PR. GitHub records all 88 merged PRs as merged by the owner's
account.

**Decision.**
- Pull requests store `merged_by` (poller: GraphQL `mergedBy`; webhooks: REST `merged_by`).
- A merge by a login in the team's reviewer pool is a person's approval. The owner
  confirmed (2026-11-25) that they merged all 88 merged PRs: 51 with GitHub's merge
  button and 37 (all before 2026-11-24 07:12 UTC) as a local merge pushed to main. So
  every merge counts, with no start date. A draft of this addendum counted only merges
  after PR #76 (2026-11-24 07:02 UTC), assuming agents had pushed the earlier ones; that
  assumption was wrong and was dropped.
- Human review stage: "N of M approved" (merged PRs merged by the human), and
  held when all of them were. Written reviews and comments are still counted and shown.
- R2 (no one approves their own work alone): an agent's PR the owner merged is not alone.
  The owner's own PRs still need an agent's review.
- A merged PR's snapshot id now includes who merged it, so each merged PR is re-stored once
  on the next sync. That also stores the commit messages of PRs collected before commits
  were kept, which is why #67 and #77 showed as "no lane" (their `Co-Authored-By: Claude`
  trailer puts them in the Claude lane).
