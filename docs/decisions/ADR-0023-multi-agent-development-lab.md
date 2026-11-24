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
