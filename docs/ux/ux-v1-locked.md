# Program Intelligence Platform — UX v1 (locked 24 Nov 2026)

Design canvas: https://claude.ai/artifact/QLp89uhmoeG8d1ZvXdUKW8 (version label "UX v1 locked"). This file is the build reference for Cursor / Claude Code.

## Headline and positioning

- Product name: **Program Intelligence Platform** (logo text "Program Intelligence").
- Front-page headline: **"Run every program from plan to launch on facts, now that agents write the code."**
- Tagline: "AI-native program management · every fact verified".
- Engine name inside Decision Studio: **Shadow-Org Simulator** ("Powered by the Shadow-Org Simulator").

## Navigation

- **Front page menu:** Portfolio · Live Cockpit · Decision Studio · AI-native PDLC · Connect your tools · Sign in · button "Open the live demo" (goes to Live Cockpit).
- **App menu (every app screen):** Portfolio · Live Cockpit · Decision Studio · AI-native PDLC · Connect your tools, plus ⌘K search, a Live indicator and the signed-in avatar. The current page is underlined (`aria-current="page"`).
- **Live Cockpit and Decision Studio** open on the last program viewed, with a switcher breadcrumb: Portfolio / Kubernetes · v1.38 ▾, and a header line: stage, Code Freeze, release date, data as of.
- **AI-native PDLC** is org/pod level, with a pod switcher ("Pod: Program Intelligence repo ▾").
- Naming: sentence case everywhere, except proper names: Program Intelligence Platform, Live Cockpit, Decision Studio, Shadow-Org Simulator.

## Screens

| # | Screen | Purpose | Key content |
| --- | --- | --- | --- |
| 1 | Front page | What it is and proof | Dark hero with 3 live programs; five stages (Plan · Build · Verify · Launch · Learn; Verify was "Freeze" until 2026-11-25, ADR-0025 addendum) with module status; three real stories (33 removed at Code Freeze, 0 of 43 merged PRs human-reviewed, 81% Kafka features linked); Built for trust scorecard; Recorded demo section (2:00, 5 chapters) |
| 2 | Portfolio | All programs at once | "Here are the live programs." Table: program, stage bar, scope, biggest bottleneck, next decision; Waiting on you; Across programs; Coming next (RAID, readiness, retros) |
| 3 | Live Cockpit | One program, live | Lifecycle bar (you are here), 5 stat tiles, **time machine** replay of #6395 (8 real dates), What happened at Code Freeze chart, Decide card, verified executive brief (#brief) |
| 4 | Decision Studio | Simulate and decide (was "Test a fix" until 2026-11-25) | Pool picker (real SIG pools), lever picker, baseline vs scenario (illustrative until the live simulator fills them), "not validated" banner with real replay numbers, measured assumptions table |
| 5 | AI-native PDLC | How the pod builds, checks and ships | Pod of 4 (human `harpreet`, Claude `claude-agent`, Cursor `cursor-agent`, Dependabot bot), 7-stage pod flow (Contract, Build, Cross-review, CI, Human review, Merge, Kept), pod metrics vs targets, pod rules checked against real PRs, next-rule chooser |
| 6 | Connect your tools | Plug in a company | 3 steps (connect, describe releases, first program filling in), connector status, trust promises |

## Visual system

- Fonts: Space Grotesk (headings), Inter (body).
- Mix of dark and light: dark (#0B1020) for the top bar, hero and "moment" sections (time machine, rule chooser, demo); light (#F6F7F9 page, white cards) for working content.
- Colors by meaning: indigo #4F46E5 actions, selection and stages; green #166534 / #DCFCE7 healthy; amber #B45309 / #FEF3C7 warning; red #B91C1C / #FEE2E2 critical; slate neutral.
- Charts: segments differ in lightness with gaps, a legend and a text description.
- Accessibility: visible focus ring on every control, text contrast ≥ 4.5:1, real buttons and links, labels on icon-only controls, touch targets ≥ 44 px.

## Honesty rules shown in the UI

- Real numbers carry a date ("data as of"). Model outputs are labeled "illustrative" or "model output". Unvalidated models show "not validated".
- Medians only from 5+ merged PRs per lane; otherwise "not enough data yet".
- Planned modules are labeled "Planned" or "Preview" and show no invented data.

## Still to design during the build

- Empty, loading and error states for every screen.
- Real charts from a chart library with tooltips.
- Phone and tablet checks.
- A 2-3 person usability test in Play mode.
- The recorded 2-minute demo video (5 chapters on the front page).

## Addendum (2026-11-26): where RAID, readiness and retro live

The app menu stays Portfolio · Live Cockpit · Decision Studio · AI-native PDLC · Connect your tools. RAID, Readiness and Retro are not new top-level items. Each is a Live Cockpit section of one release, next to Overview, Dependencies, Executive update and Link review:

- `/projects/{project}/releases/{name}/raid`
- `/projects/{project}/releases/{name}/readiness`
- `/projects/{project}/releases/{name}/retro`

⌘K lists them as "Live Cockpit · RAID", "Live Cockpit · Readiness" and "Live Cockpit · Retro" for the release in the URL. Launch, on the lifecycle bar, the front-page five stages and the portfolio stage bar, links to that release's readiness. Learn links to that release's retro only when the portfolio says this program has a retro. The screen rules are ADR-0029 and ADR-0031.
