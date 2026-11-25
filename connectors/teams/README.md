# Team connectors

Each YAML file here is one cross-functional team. **Kubernetes is a live example**, not the product.

## Add a team (minimum new code)

1. Copy `_template.yaml` → `<team-id>.yaml`.
2. Set `planning` (GitHub issues or Jira), `code.repos`, `calendar.path`, and `link_pack`.
3. Add a release calendar YAML (same schema as `collectors/github_poller/release_calendar.yaml`).
4. If `planning.source: github`, run:
   ```bash
   make backfill TEAM=acme RELEASE=v1.0
   ```
5. If `planning.source: jira`, you need the Jira collector (stub today) — config is already valid.

**You should not fork** `engine/`, `pipeline/`, or `api/`. New linker behaviour goes in a **link pack** (`linker/packs/`), not scattered conditionals.

| Field | Purpose |
|---|---|
| `id` | Filename stem; CLI `--team` |
| `display_name` | UI label (“Kubernetes”, “Apache Kafka”) |
| `project` | Release key prefix (`kubernetes:v1.38`) |
| `link_pack` | `kep` or `jira_key` |
| `planning` | Where the plan lives |
| `code.repos` | Where PRs/reviews/CI live |
| `calendar.path` | Freeze / release dates |
| `code_freeze_label` | Optional. Your name for the `code_freeze` date (default "Code Freeze"; Kafka: "Feature Freeze"). The Verify stage starts on it. |
