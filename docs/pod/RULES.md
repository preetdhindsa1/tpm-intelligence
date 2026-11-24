# The pod rules

The rules for a pod of 1 human, 2 AI agents and 1 bot (Dependabot). Each rule is
short on purpose. Where a rule can be enforced by a tool, the tool is named.
`AGENTS.md` points every agent here.

## Who is in the pod

The label and the branch prefix name the same lane: `harpreet` and `harpreet/`,
`claude-agent` and `claude/`, `cursor-agent` and `cursor/`. The first match wins:
label, then branch prefix, then commit trailer. A GitHub login is never a lane.

| Member | Lane | Writes | Reviews | Never |
| --- | --- | --- | --- | --- |
| Human (owner) | `harpreet`, `harpreet/<issue>-<slug>` | The contract and the hard code | Every PR, in review windows. Merges and releases | Merges own high-risk code without both agents' review and a second read |
| Claude Code | `claude-agent`, `claude/<issue>-<slug>` | Implementation PRs in its lane | Cursor's, the human's and bot PRs | Approves, merges, edits approved tests |
| Cursor agent | `cursor-agent`, `cursor/<issue>-<slug>` | Implementation PRs in its lane | Claude's, the human's and bot PRs | Same as Claude Code |
| Dependabot (bot) | No label: `dependabot/…` branches, author `dependabot[bot]` | Dependency and security update PRs | Nothing | Merges itself. Is never counted as an agent lane |

## Who decides

- **R1. The human owns every decision.** Agents draft, test and review. Only the
  human approves the contract, merges and releases.
- **R2. No one approves their own work alone.** Agents review each other. Both
  agents review the human's PRs. *(Branch rules + PR template.)*
- **R3. Agents and bots never merge.** *(Branch rules: only the owner can merge;
  no Dependabot auto-merge.)*

## How work starts

- **R4. One issue, one lane, one branch, one PR.** Every issue is labeled
  `claude-agent`, `cursor-agent` or `harpreet` before work starts. Branches are
  `claude/<issue>-<slug>`, `cursor/<issue>-<slug>`, `harpreet/<issue>-<slug>`.
  Dependabot PRs need no issue and no lane label: they are classified from the
  `dependabot/` branch and the `dependabot[bot]` author. *(Lane-label workflow.)*
- **R5. Contract first.** The human approves the spec and acceptance tests
  before any code is written. *(Issue template, `templates/contract.md`.)*
  Bot updates are the exception: the contract is "existing tests still pass".
- **R6. Every issue has a risk tier.** `risk:low`, `risk:medium` or `risk:high`.
  High means data model, public API, security, payments or privacy.
  *(PR guardrails workflow fails PRs without exactly one tier.)*
- **R7. Lanes own areas of the code.** Two agents do not change the same files
  at the same time. If they need to, the human splits the issue.

## How code is written

- **R8. Small PRs.** Under 400 changed lines, excluding lock files and
  generated files. *(PR guardrails workflow; `size:exception` label is the
  human's call.)*
- **R9. WIP limit: two open PRs per agent.** An agent at its limit finishes,
  fixes or closes a PR before opening another. Dependabot has its own limit
  (R26).
- **R10. Approved tests are locked.** Agents do not change files under
  `tests/acceptance/`. Changing the contract is the human's job.
  *(PR guardrails workflow.)*
- **R11. No secrets, no customer data in prompts.** *(Secret scanning.)*
- **R12. Every PR says who wrote it.** A `Lane` line and an AI-assistance
  statement: written by an agent, written by the human, the human edited AI
  output, or opened by a bot. Agent commits carry their trailer
  (`Co-Authored-By: Claude`, `Co-authored-by: Cursor Agent`). *(PR template.)*

## How code is reviewed

- **R13. Cross-review before the human.** The other agent reviews every agent
  PR; both agents review the human's PRs; one agent reviews every bot PR. The
  human reviews only PRs that passed cross-review and CI.
- **R14. Review windows.** The human reviews twice a day at set times, oldest
  ready PR first. Agents and the bot batch for those windows.
- **R15. Review by risk tier.** Low: quick check. Medium: one full review.
  High: both agents, CI, a full review with the high-risk checklist, and for the
  human's own code a second read in a later window.
- **R16. Two-round rule.** A third review round means the contract is wrong.
  Stop commenting; fix the spec or tests first. *(PR guardrails workflow labels
  `back-to-contract` on the second "changes requested".)*
- **R17. Three red CI runs go to the human.** An agent does not loop forever.
- **R18. Repeated comments become rules.** If the human writes the same review
  comment twice, it becomes a line in `CLAUDE.md` / `AGENTS.md`.

## How the human spends the day

- **R19. Review first, write after.** If the review queue is over the WIP limit,
  the human reviews before writing new code.
- **R20. The human writes 1 to 1.5 hours a day,** and only what an agent should
  not: high-risk code, cross-cutting design, the hard parts.

## How we know it works

- **R21. Measure, don't claim.** Velocity is merged, kept and released changes,
  never PRs opened. Numbers come from real PRs (`metrics/pr_churn.py`), never
  from estimates.
- **R22. Small samples say "not enough data".** No median from fewer than 5
  merged PRs in a lane.
- **R23. Review the rules monthly.** Keep a rule only if the data says it helps.

## Bots in the pod

- **R24. A bot is a pod member, not an agent.** Dependabot gets its own bot lane
  from its branch prefix and author, never from a label. It is never mapped to an agent
  lane, and its PRs never count toward an agent's numbers.
- **R25. Bot PRs get a risk tier by rule.** Patch and minor updates to
  development dependencies: `risk:low`. Runtime dependencies, major versions or
  security updates: `risk:medium`, or `risk:high` when they touch auth, crypto,
  payments or privacy. *(Labeler rules on the update type; the human can raise
  the tier.)* One agent reads the changelog and checks for breaking changes
  before the human looks.
- **R26. Limit bot noise.** Weekly schedule, grouped updates and an
  `open-pull-requests-limit` in `.github/dependabot.yml`. A bot PR closed
  without merging is churn: the human still spent attention on it. Track bot PRs
  per week and the share closed unmerged.
- **R27. Bot PRs are review load.** They count in the human review load and the
  review queue, like every other PR, so the pod plans for them.
