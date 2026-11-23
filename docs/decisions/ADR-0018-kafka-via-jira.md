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
   New Feature, **or** has sub-tasks (an umbrella), **or** names a KIP. (The KIP part
   was tightened after measuring; see "Measured" below.) Bugs and loose improvements
   stay off the feature list but still count as reviewer and CI load. A sub-task's PRs
   roll up to its umbrella.
2. **Dates: Jira release dates only, for now.** Each release gets `release_at` from its
   Jira version and `cycle_start_at` from the release date of the previous x.y.0
   version. No freeze dates, so forecasts that need Code Freeze show "no freeze date"
   instead of a number. Hand-entered freeze dates from the Kafka release-plan page are
   deferred (`connectors/teams/kafka-calendar.yaml` stays a placeholder, unused).
   Measured 2026-11-22: 4.5.0 has **no release date** in Jira yet.

## Built after the decisions

- **Feature rule in the engine.** `Feature.is_release_feature`: type feature, or has
  sub-tasks, or has a design doc (KEP `kep.yaml` or KIP, carried as
  `work_item.spec_observed`). Sub-tasks never count. Every work item stays in
  `World.features`, so a sub-task's PRs **roll up** to its umbrella, with the sub-task
  in the link evidence (`via_sub_task`). Kubernetes is unchanged: every KEP issue is a
  feature (feature and link counts identical for v1.33-v1.38 before and after).
- **Remote links** (Jira's GitHub integration) become verified `remote_link` links
  (confidence 0.85). Jira does not say when a link was made, so it is dated when the
  collector saw it and never appears in a backtest world before that.
- **Jira keys have numbers** (`KAFKA-20682` -> 20682), so feature pages are
  `/features/20682` and the UI labels them by key.
- **PRs for `apache/kafka`**: the GitHub poller runs code-only for a Jira team (no
  planning issues, no release event) over the window the Jira version dates give:
  previous x.y.0 release to this release day, or now while it is unset.
- **One world per project.** `TeamConfig.owns` assigns every event subject (release
  key, planning key, PR repo) to a team, and the API projects one project at a time, so
  Kafka PRs are never Kubernetes reviewer load. `finished_releases` only returns the
  same project's releases: projects never calibrate each other. Bare release names
  (`4.4.0`, `v1.38`) resolve to the only release with that name, else to the default
  project.
- **Wording.** "SIG"/"KEP" for Kubernetes, "component"/"KIP" for Kafka
  (`web/lib/vocab.ts`). Without a freeze date odds and merge dates say "No Code Freeze
  date" instead of a number.

## Measured (2026-11-23, `scripts/measure_kafka_linking.py`)

| | 4.4.0 (shipped) | 4.5.0 (open) |
|---|---|---|
| Jira issues collected (both releases) | 643 | |
| Features ever in / in now | 63 / 50 | 38 / 35 |
| ...by rule: New Feature / umbrella / KIP | 13 / 7 / 43 | 3 / 11 / 24 |
| Features with a verified PR | 51 (81%) | 30 (79%) |
| `apache/kafka` PRs in the window | 1,696 | 459 |
| PRs naming any KAFKA key | 1,178 | 301 |
| PRs with a verified link to a feature | 161 | 31 |
| Verified links reached through a sub-task | 89 | 82 |

**Finding: the KIP part of the rule is too loose.** Of the 43 features in 4.4.0 that
qualify only by naming a KIP, 22 are **bugs** and 34 name the KIP only in the
description (e.g. KAFKA-20253 "High CPU loop on consumer after failed
re-authentication" mentions KIP-848). Raised with the owner.

**Revised rule (2026-11-23, option A, the recommendation; easy to change).** An issue is
a Kafka feature if it is a New Feature, **or** an umbrella with sub-tasks, **or** a
non-bug that names its KIP **in the title or through a remote link** to the KIP page. A
KIP named only in the description no longer counts, and bugs never count through a KIP.
The collector records where the KIP was found (`spec_source`); for events stored before
that field existed, the engine checks the title itself.

Re-measured with the revised rule (2026-11-23, after re-syncing Jira):

| | 4.4.0 (shipped) | 4.5.0 (open) |
|---|---|---|
| Features ever in / in now | 26 / 19 | 17 / 16 |
| ...by rule: New Feature / umbrella / KIP | 13 / 7 / 6 | 3 / 11 / 3 |
| Features with a verified PR | 21 (81%) | 12 (71%) |
| PRs with a verified link to a feature | 114 of 1,696 | 23 of 459 |
| Verified links reached through a sub-task | 89 | 82 |

All 6 KIP features in 4.4.0 are stories, not bugs. Two are borderline ("Create integration
tests for KIP-1035 changes", "Revert public API changes from KIP-1238"). Removal history
works: 6 of the 7 features dropped from 4.4.0 now sit in 4.5.0. Coverage counts whether
a link exists, not whether it is right; precision is not labelled yet.

## Limitations

- No freeze dates, so no odds or merge-date forecasts for Kafka yet; flags and links
  still work. Deferred by the owner.
- Kafka components are not mapped to teams yet, so team views show "no team label".
- An umbrella outside the release whose sub-tasks are in it is not a release feature;
  those sub-task PRs count as unlinked load.
