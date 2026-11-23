# ADR-0018: Apache Kafka via Jira (Phase 3 M3)

- **Status:** accepted (2026-11-22): feature rule and dates decided by the owner
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

## Decided by the owner (2026-11-22)

1. **A Kafka "feature"** (the KEP analog) is an issue that targets the release and is a
   New Feature, **or** has sub-tasks (an umbrella), **or** names a KIP (`KIP-123` in its
   summary or description, or a remote link to a KIP page). Bugs and loose improvements
   stay off the feature list but still count as reviewer and CI load. A sub-task's PRs
   roll up to its umbrella.
2. **Dates: Jira release dates only, for now.** Each release gets `release_at` from its
   Jira version and `cycle_start_at` from the release date of the previous x.y.0
   version. No freeze dates, so forecasts that need Code Freeze show "no freeze date"
   instead of a number. Hand-entered freeze dates from the Kafka release-plan page are
   deferred (`connectors/teams/kafka-calendar.yaml` stays a placeholder, unused).
   Measured 2026-11-22: 4.5.0 has **no release date** in Jira yet.

## Still to build after the decisions

- Engine: feature selection per team, and keys like `KAFKA-19831` (features are numbered
  from `repo#N` today).
- PR collection for `apache/kafka` over the release window. Project-scoped API routes and
  per-project UI wording (ADR-0014).
- Linking coverage measured on one Kafka release; then Kafka appears on the home page.
