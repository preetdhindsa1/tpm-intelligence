# ADR-0003: Team connectors (plug-and-play config)

- **Status:** accepted
- **Date:** 2026-11-22

## Context

The product is program intelligence for **any cross-functional team**. Kubernetes and
Apache Kafka are live proof datasets, not the product. Phase 1 hard-coded K8s repos,
KEP linking, and “Kubernetes …” UI copy, so onboarding another team meant editing core
modules.

## Decision

1. **`connectors/teams/<id>.yaml`** describes a team: display name, project key, planning
   source (GitHub issues or Jira), code repos, calendar path, and `link_pack`.
2. **Collectors read the team file** (`--team kubernetes`). They do not embed repo names.
3. **Linker packs** (`linker/packs/`) isolate planning-style rules (`kep`, `jira_key`).
   `engine/links.py` selects the pack from the team config by release project.
4. **API/UI** show `display_name` from the connector, not a hard-coded product brand.

Adding a GitHub-planned team should require: copy `_template.yaml`, add a calendar, run
`make backfill TEAM=… RELEASE=…`. No forks of `engine/`, `pipeline/`, or `api/`.

## Alternatives considered

- **Per-company forks of the poller.** Rejected — diverges forever.
- **Only runtime env vars.** Rejected — not reviewable; calendars and link packs need files.
- **Full multi-tenant admin UI first.** Deferred — YAML is enough to prove plug-and-play.

## Trade-offs

- Jira planning still needs `collectors/jira` (config is ready; collector is not).
- KEP extractors remain K8s-shaped inside the `kep` pack; that is intentional.
- Engine resolves pack via `connectors.load` (cached YAML). Still no network/DB I/O.
