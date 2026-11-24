# Program Intelligence Platform: end-to-end plan

The plan both agents work from, wave by wave. Store it in the repo at `docs/plan/e2e-plan.md`. Rules live in `CLAUDE.md`, `AGENTS.md` and `docs/pod/RULES.md`; the UX is locked in `docs/ux/ux-v1-locked.md`.

**The product:** an AI-native, end-to-end program management platform that a company plugs into its own tools. It covers the whole program, from plan to launch (Plan · Build · Freeze · Launch · Learn): Portfolio, Live Cockpit, Decision Studio (Shadow-Org Simulator), AI-native PDLC, RAID, release readiness and retros. Rules and statistics compute every fact, AI explains, a fact checker verifies, and a person approves anything that leaves.

**The team (the pod):** Harpreet (owner, `harpreet`), Claude Code (`claude-agent`), Cursor (`cursor-agent`), Dependabot (bot lane).

## How every wave runs

1. **Harpreet opens the wave:** creates its issues (lane label + one risk label + acceptance criteria), and approves both agents' plans.
2. **Split by ownership, not by layer.** Claude owns the backend (`api/`, `engine/`, `collectors/`, `simulator/`, `pipeline/`, `agents/`, `verify/`, `evals/`, `scripts/`, `infra/`), `README.md`, `docs/` (except `docs/ux/`) and `CLAUDE.md`. Cursor owns `web/` (except the pages a wave gives to Claude) and `docs/ux/`. A wave can hand a whole screen to one agent; it then owns that screen's folders.
3. **Contract first.** When a screen needs new data, Claude's first PR in the wave is the JSON contract (`docs/api/`) with exact examples. Cursor builds against the examples while Claude builds the endpoint.
4. **Pod rules:** one issue, one branch, one PR; under 400 changed lines; at most 2 open PRs per agent; labels `needs-cross-review` → (other agent reviews with comments) → `needs-human-review` → Harpreet merges. Review comments come before new work. Never wait idle: move to the next unblocked issue.
5. **Honesty:** real numbers carry a date; model outputs say "illustrative" or "model output"; unvalidated models say "not validated"; medians only from 5+ merged PRs in a lane; unmeasured = "TBD (not yet measured)".
6. **Docs and ADRs** in the same PR as the change. ADR numbers are reserved below so two agents never take the same number. Cursor puts README or roadmap text it needs under "Docs for Claude" in its PR; Claude adds it.
7. **A wave is done** when every issue's acceptance criteria are checked, CI is green, it is deployed, and the README results table shows the new measured numbers (or "TBD" with the reason).

## Reserved ADR numbers

| Wave | Cursor | Claude |
| --- | --- | --- |
| 1 · UX v1 | ADR-0024 Front end: shell, navigation, color system, states | ADR-0025 Portfolio rules; ADR-0023 addendum (pod facts) |
| 2 · Prove it | (addendum to ADR-0024 if needed) | ADR-0012 addendum (simulator validation); ADR-0026 Results API |
| 3 · AI-native PDLC across teams | ADR-0027 PDLC views for teams | ADR-0028 AI-era delivery signals |
| 4 · RAID | ADR-0029 RAID review UI | ADR-0030 Notes source and RAID model |
| 5 · Readiness + retros | ADR-0031 Readiness and retro UI | ADR-0032 Readiness criteria and retro facts |
| 6 · Plug-in platform | ADR-0033 Onboarding and org settings | ADR-0034 Tenants and isolation; ADR-0035 Connector framework |
| 7 · Hardening and proof | (addenda) | ADR-0036 Demo mode |

---

## Wave 0 · Set up (Harpreet, 15 minutes)

- [ ] One `harpreet/` PR adding: the new `CLAUDE.md`, `docs/ux/ux-v1-locked.md`, `docs/pod/RULES.md`, `docs/plan/e2e-plan.md`. Merge it.
- [ ] Labels exist: `cursor-agent`, `claude-agent`, `harpreet`, `needs-cross-review`, `needs-human-review`, `risk:low`, `risk:medium`, `risk:high`.
- [ ] Branch rules on `main`: require a PR and passing CI; only the owner merges; block force pushes.
- [ ] Create the Wave 1 issues: `bash create-ux-v1-issues.sh`.

## Wave 1 · UX v1 (today, a few hours)

Goal: the locked UX in the real app, on real data. Full prompts: `agent-prompts-ux-v1.md`.

| Cursor (18 points) | Claude (11 points + stretch) |
| --- | --- |
| A. App shell and navigation (first) | 1. GET /portfolio + JSON contract (first) |
| B. Live Cockpit with the time machine | 2. Pod facts on GET /lab |
| C. Decision Studio | 3. AI-native PDLC page (after A merges) |
| D. Portfolio page | 4. Docs sync |
| E. Front page + recorded demo section | Stretch: simulator review-wait investigation |
| F. Connect your tools page | |
| G. Empty, loading and error states | |

**Done when:** the live site shows all six screens with real data; old URLs redirect; the PDLC page shows cross-reviews and human-reviewed merges from this sprint's own PRs.

## Wave 2 · Prove what is built (1–2 days)

Goal: turn "built" into "proven", and make Harpreet's review tasks quick.

| Cursor | Claude |
| --- | --- |
| Review tools: a page to label the 70 linking cases, confirm or reject AI link suggestions, and review fact-checker labels (keyboard-friendly, progress shown) | GET /results: every measured result with date, value, pass/fail and source file (replaces hard-coded numbers on the front page and scorecard). ADR-0026 |
| Front page "Built for trust" and README scorecard read from GET /results | Simulator validation: fix the review-wait definition with evidence, re-run validation on releases it was not tuned on, report pass or fail honestly. ADR-0012 addendum |
| | Linking precision per method and reviewed AI-suggestion precision, computed from Harpreet's labels and published |
| | Confirm v1.39 daily forecast snapshots run in the cloud; scoring command ready for when v1.39 ships |

**Harpreet:** label the linking cases and review suggestions using the new page (about 2 hours).
**Done when:** linking precision and suggestion precision are published; the simulator passes validation or the README says exactly why not.

## Wave 3 · AI-native PDLC across teams (2–3 days)

Goal: the AI-era signals for every team, not only this repo.

| Cursor | Claude |
| --- | --- |
| PDLC page pod switcher works for Kubernetes and Kafka (pods = reviewer pools / SIGs) | Verify first: how Kubernetes PRs disclose AI use (real samples, phrases, frequency), then per-team disclosure patterns in connector config; AI-assisted share reported as a minimum |
| Trend charts per release and pool: time to first human review, review depth, PR size, rework | Signals in `engine/`: time to first human review, review capacity vs demand per pool, review depth, PR size (generated files excluded), rework (reverts, follow-up fixes, same-file changes within 30 days). Minimum group size 10. ADR-0028 |
| AI-assisted vs other comparison, only for groups of 10+, with the "minimum" caveat | Feed signals into flags and the forecast only if a backtest shows they help |
| Decision Studio: AI-era levers (PR volume ×, AI first-pass share, PR size cap, reviewers vs engineers) | Simulator AI-era what-ifs behind those levers, labeled as assumptions until measured |

**Done when:** published for Kubernetes v1.36–v1.38: AI-assisted share (minimum), time to first review, review depth and rework, with dates.

## Wave 4 · RAID tracker (2–3 days)

Goal: risks, actions, issues, decisions and questions from meetings and tickets, with the human approving.

| Cursor | Claude |
| --- | --- |
| RAID page per workstream: review queue (confirm, edit, reject), current tracker, history | Verify first: a public meeting-notes source (e.g. Kubernetes release-team notes) that can be fetched by API or export, or clearly labeled synthetic notes. Evidence in ADR-0030, then wait for Harpreet's choice |
| "Copy as Markdown / HTML" to publish; nothing posts automatically | Notes connector; RAID extractor agent (verbatim quotes checked word for word); deterministic IDs `{WORKSTREAM}-{TYPE}-{SEQ}`; merge, dedupe and lifecycle |
| RAID items in the Live Cockpit and in Portfolio "Waiting on you" | Confirmed risks and decisions feed the risk analyst and VP update; evals (30+ labeled excerpts) gated in CI |

**Done when:** the eval gate passes and real notes produce confirmed RAID items on the page.

## Wave 5 · Release readiness and retros (2 days)

Goal: close the lifecycle: Launch and Learn.

| Cursor | Claude |
| --- | --- |
| Readiness page: each criterion with its evidence, the go/no-go decision with who and when | Readiness criteria engine, configurable per team (code merged or excepted, no open critical flags, CI green, risks reviewed, docs merged); decision store; AI summary from verified facts only |
| Retro page: what slipped, when the first warning appeared, patterns per pool | Retro facts from forecast snapshots (first warning date per slip), patterns across releases (per pool, never per person) |
| Launch and Learn stages light up in the Live Cockpit and Portfolio | Backtest on v1.36–v1.38 and Kafka 4.4.0: would readiness have said no-go where late exceptions happened? ADR-0032 |

**Done when:** the readiness backtest is published honestly.

## Wave 6 · Plug-in platform for companies (3–4 days)

Goal: a company signs up, connects its tools, and sees only its own data.

| Cursor | Claude |
| --- | --- |
| Connect your tools becomes real: sign up, create an organization, install the GitHub App, connect Jira, set the calendar and link pack, watch the first backfill | Tenants: organizations, members, roles; tenant ID on every row; Postgres row-level security; migration making the public demo one tenant. ADR-0034 |
| Organization settings: members and roles, connectors, usage limits, data export and deletion | Connector framework: team configs as per-tenant records (YAML kept for the demo), secrets per tenant, audit log, deletion, usage limits. ADR-0035 |
| | One new connector (GitLab or Linear) after verifying what public or sandbox data exists |
| | Permission tests in CI proving one tenant cannot see another's data |

**Done when:** a second test organization connects a repo and sees only its own data, proven by tests.

## Wave 7 · Hardening, proof and launch (1–2 days)

| Cursor | Claude |
| --- | --- |
| Accessibility audit (automated + keyboard pass), phone and tablet checks | Load test with two tenants and a burst of webhooks; fix bottlenecks |
| Embed the recorded demo video in the front page | Demo mode with a cached dataset, so the demo works if GitHub or Jira is slow. ADR-0036 |
| | Backtests for every module in one results table, with weak spots; README final pass; interview study material synced with what is built |

**Harpreet:** record the 2-minute demo (5 chapters), publish the LinkedIn posts with real numbers.
**Done when:** a stranger can read the README, see measured results, watch the demo and use the live app.

---

## Prompt to start any wave (both agents)

```
Read CLAUDE.md, AGENTS.md, docs/pod/RULES.md, docs/ux/ux-v1-locked.md and docs/plan/e2e-plan.md. We are in Wave <N>. Your lane is <claude-agent | cursor-agent>.

1. Run `gh issue list --label <your lane> --state open` and pick only this wave's issues.
2. Write a short plan (PRs in order, files, tests, risks, which reserved ADR you will write) and STOP for Harpreet's approval.
3. Work by the plan's rules: your folders only; contract first when a screen needs new data; one issue per PR; labels (lane, one risk, needs-cross-review); under 400 lines; at most 2 open PRs; never merge.
4. Before each new task: answer review comments on your PRs, then cross-review the other agent's needs-cross-review PRs (comments only) and switch them to needs-human-review.
5. Never wait idle; never invent numbers; update ADRs and docs in the same PR.
6. After each PR: a short summary (what changed, how tested, what is next, anything Harpreet must do).
```

For Wave 1, use the detailed prompts in `agent-prompts-ux-v1.md`.
