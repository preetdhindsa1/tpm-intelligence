# ADR-0014: Multi-project navigation (project/release switcher, home page, URLs)

- **Status:** accepted (Phase 2, between M6 and M7)
- **Date:** 2026-11-22

## Context

The dashboard should serve more than one project: Kubernetes now, Apache Kafka (Jira plan
plus GitHub code) once the Jira collector lands. The data model already keys releases by
`(source, project, name)`, and team connector files (`connectors/teams/*.yaml`) declare
projects. The web app did not: every page URL was `/releases/{name}`, the home page
redirected to the newest release, and page titles said "Kubernetes". Release names are
only unique inside a project, so a name-only URL can point at the wrong release.

The owner asked for the UI part only, with Kubernetes as the only project until Jira data
is collected.

## Decision

- **URLs carry the project:** `/projects/{project}/releases/{name}/...` (project lower-cased).
  An unknown project/release pair returns 404. Old `/releases/{name}/...` links redirect
  when exactly one project has that release name, and go to the home page otherwise.
- **A two-level switcher** above every release page: `All releases / Project ▾ / Release ▾`.
  Picking a release keeps the current section (Dependencies, Simulations, Reports, Link
  review); a feature page is dropped because the feature may not exist in the other
  release. Picking a project opens its newest release. Two linked pickers, not two
  independent dropdowns, so impossible pairs cannot be chosen.
- **A "Release health" home page** lists each project with data: one card for its current
  release (the earliest not yet released, else the latest) with the next milestone and
  the same five facts as the dashboard tiles, then a table of every release. Numbers are
  never summed across projects: their scopes and definitions differ.
- Page titles use the project's display name from the API.
- Only projects with collected data appear. The Kafka connector file exists, but its
  calendar is a placeholder and no Kafka events are collected, so Kafka is not shown.

## Alternatives

- **One extra dropdown in the header.** Allows impossible project/release pairs and still
  needs project-scoped URLs underneath.
- **Keep name-only URLs.** Breaks as soon as two projects share a release name.
- **Show Kafka now as "not connected".** Rejected for now: the owner asked for
  Kubernetes only until the data lands, and its placeholder dates must not be shown.

## Trade-offs and limits

- **The API is still name-keyed and single-project** (`ReleaseService` builds keys as
  `{project}:{name}` for one configured project). The web layer checks the
  project/release pair before calling it. Project-scoped API routes come with the Jira
  milestone.
- **Labels are still Kubernetes terms** (SIG, KEP, Enhancements Freeze, "removed at Code
  Freeze"). A per-project vocabulary profile from the API is planned with the Jira data,
  together with the Kafka meaning of "removed" (Fix Version taken off).
- The home card's facts need the release view, which can take about 40 s to recompute
  when its cache expires; the card shows dates at once and streams the facts in.

## Update (2026-11-22): front page

`/` is now a front page that explains the product. It shows:
- the pipeline, with each step marked as deterministic, AI then fact-checked, or human;
- a live pulse of the current release, from the API's computed facts;
- a scorecard of measured results.

Release health moved to `/releases`. The scorecard values are copied from the README's
"Measured results" table into `web/lib/measured.ts`, each with its date. Failing and
unmeasured results are shown as such.
