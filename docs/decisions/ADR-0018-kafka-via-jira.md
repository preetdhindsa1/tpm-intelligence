# ADR-0018: Apache Kafka via Jira (Phase 3 M3)

- **Status:** proposed: collector built; the feature definition and calendar await the owner
- **Date:** 2026-11-22

## Context

Kafka plans in Apache Jira (project KAFKA) and ships code in `apache/kafka`. The event
model is source-neutral (ADR-0001), so Jira must produce the same events as GitHub.
Measured on 2026-11-22 through the public REST API:
- 4.5.0 is the open feature release; 4.4.0 shipped on 2026-10-26.
- 4.4.0 contains 117 bugs, 71 improvements, 26 tasks, 12 tests, 9 new features, 1 wish and
  **73 sub-tasks under 24 umbrella issues**. Only 3 of the umbrellas name a KIP in the
  summary. There are no Epics.

## Decided (built)

- **API only**, anonymous, at least 1 s between requests, and HTTP 429 waited out by the
  shared client. Changelogs that search truncates are fetched in full.
- **Issues are found by fix version, including issues that used to have it**
  (`fixVersion was in (...)`), so a feature dropped from a release shows as removed
  (CLAUDE.md section 6).
- **Fix versions set at creation are rebuilt** by undoing the changelog from the
  current state. Jira does not log them: KAFKA-21181 got 4.2.0 and 4.3.0 at creation.
- **Status categories** come from Jira's `statusCategory`. Changelog entries carry names
  only, so they use the KAFKA workflow map; a team connector may override it.
- **Remote links to GitHub PRs** become `reference.observed` (raw evidence). Who changed an
  issue is never read.
- `python -m collectors.jira --team kafka --release 4.5.0`.

## Open (owner)

1. **What counts as a Kafka "feature"** for release health (the KEP analog)? Proposal:
   an issue targeting the release that is a New Feature, **or** has sub-tasks (an
   umbrella), **or** links a KIP page in its summary, description or remote links. Bugs and
   loose improvements stay out of the feature list but still count as reviewer and CI load.
2. **Freeze dates.** Jira versions carry release dates only. Proposal: enter KIP freeze,
   feature freeze, code freeze and release day by hand from Kafka's public release-plan
   page, with the link, in `connectors/teams/kafka-calendar.yaml`. The current file is a
   placeholder and is not used.

## Still to build after the decisions

- Engine: feature selection per team, and keys like `KAFKA-19831` (features are numbered
  from `repo#N` today).
- PR collection for `apache/kafka` over the release window. Project-scoped API routes and
  per-project UI wording (ADR-0014).
- Linking coverage measured on one Kafka release; then Kafka appears on the home page.
