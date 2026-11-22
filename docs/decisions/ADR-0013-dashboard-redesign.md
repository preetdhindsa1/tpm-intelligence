# ADR-0013: Dashboard redesign (graph, outcomes, verified brief)

- **Status:** accepted (Phase 2 M6)
- **Date:** 2026-11-22

## Context

The owner shared a mockup (2026-11-21) and asked for it in light colours:
- a left navigation;
- a release dependency graph with red "delay risk" nodes;
- a Monte Carlo "release slip probability" curve in days of delay;
- a "Verified AI executive brief".

CLAUDE.md rules that shape it:
- every number comes from deterministic code (§2.1);
- forecasts are ranges, labelled "not validated" when they fail their backtest (§2.5,
  ADR-0005);
- humans approve the executive update (§2.4).

## Decision

- **Layout:**
  - a sidebar (Dashboard, Dependencies, Simulations, Reports, Link review);
  - five stat tiles;
  - three panels: graph, outcome or odds chart, executive brief;
  - the feature table, kept below.
- **Colours:** light slate surfaces. Red, amber and green are the status palette from the
  dataviz reference (`#d03b3b`, `#fab219`, `#0ca30c`, plus `#ec835a` and a neutral). They
  are used only for state and always next to a text label.
- **Dependency graph** (`GET /releases/{r}/graph`, React Flow + dagre):
  - the engine's existing graph: release → features → verified PR links, plus "blocks"
    edges stated in PR text;
  - each feature is coloured by its highest flag severity, with a badge for its most
    important flag;
  - the dashboard preview shows the 8 most severe features with their main PR only;
  - the Dependencies page shows all features, main PRs by default, with options for all
    linked PRs, merged PRs and removed features. It opens at a readable zoom and is
    panned, because 70 features and ~950 PRs cannot fit on one screen readably.
  - AI-suggested links are never drawn.
- **Chart panel:**
  - **Before Code Freeze:** each feature's odds of landing, as a dot with its 10th–90th
    percentile range and the base rate, labelled "not validated".
  - **After Code Freeze:** what happened, as facts (`GET /releases/{r}/summary`): landed;
    landed but PRs merged after freeze; landed with the main PR still open; removed then
    re-added; removed at Code Freeze; removed before freeze.
  - It is a single-series bar chart with a hover list of features and a table view.
- **Executive brief:**
  - the newest approved update, else the newest draft, labelled "Draft #n, awaiting TPM
    approval", and "facts changed since drafting" when stale;
  - each line carries a ✓ because the fact checker verified it before it was stored;
  - no AI runs when the page loads.

## What was not copied from the mockup, and why

- **"Probability of a 12-day slip" curve.** The engine forecasts whether each feature
  lands by Code Freeze, not how many days a release slips. Drawing that curve would mean
  inventing a model. It is a candidate for M7.
- **"Reallocating 3 TPMs reduces risk by 45%."** Nothing computes this. The simulator's
  what-ifs are on their own page and are not validated (ADR-0012).
- **"Iterations: 10,000 / 95% CI."** We show the real settings: 20 replications × 500
  draws, 10th–90th percentile.

## Decision on outcome categories (2026-11-22)

- **The problem:** ADR-0005's outcome is "still in the release 3 days after Code Freeze".
  Ten v1.38 features were removed at freeze and re-added within 3 days, so they counted as
  "landed" while the "Removed at Code Freeze" tile counted them as removed.
- **The decision:** on the dashboard, a feature with a `removed_at_freeze` flag that is
  back in the release is always "Removed, then re-added".
- **The result:**
  - the tile and the chart agree (33 removed = 16 still out + 17 re-added);
  - "Landed" means never removed at freeze;
  - a test checks the agreement.
- **Not affected:** the forecast's own outcome definition is unchanged.

## Alternatives considered

- **Dark theme as in the mockup.** The owner asked for light colours.
- **A force-directed ("hairball") graph like the mockup.** It is unreadable at this size.
  A layered left-to-right layout keeps release → feature → PR order.
- **Server-side graph layout.** Layout is presentation. dagre in the browser keeps the API
  to plain facts.

## Trade-offs and consequences

- Three new web dependencies: `@xyflow/react`, `@dagrejs/dagre`, `recharts`.
- The dashboard makes four API calls (features, summary, graph, updates), all served from
  the same cached release view.

## AI vs rules

The only AI content is the executive brief. It was generated earlier, fact-checked claim by
claim (ADR-0008, ADR-0010), and is shown as stored. Every count, colour and graph edge comes
from rules and the engine.
