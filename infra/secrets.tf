# Secrets live in Secret Manager, never in code or git (CLAUDE.md section 10).
# The GitHub token is added by hand after apply (read-only scope):
#   gcloud secrets versions add github-token --data-file=-
# Generated values (DB password, action-signing and session secrets) are written by
# Terraform, so the state file is sensitive and lives in a locked-down GCS bucket.

resource "google_secret_manager_secret" "github_token" {
  secret_id = "github-token"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# Anthropic API key for the agents (phase 2), added by hand like the GitHub token.
resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.database_url.id
  # Cloud Run mounts the Cloud SQL connector socket at /cloudsql (see run.tf).
  secret_data = "postgresql+psycopg://${google_sql_user.app.name}:${random_password.db.result}@/${google_sql_database.app.name}?host=/cloudsql/${google_sql_database_instance.db.connection_name}"
}

# Sign-in (ADR-0016). Web and API share the action-signing secret; Auth.js uses its own.
# The GitHub OAuth app's ID and secret are added by hand, like the GitHub token:
#   printf %s "$ID" | gcloud secrets versions add auth-github-id --data-file=-
resource "random_password" "action" {
  length  = 64
  special = false
}

resource "random_password" "auth" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret" "generated" {
  for_each  = toset(["tpm-action-secret", "auth-secret"])
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "generated" {
  for_each = {
    "tpm-action-secret" = random_password.action.result
    "auth-secret"       = random_password.auth.result
  }
  secret      = google_secret_manager_secret.generated[each.key].id
  secret_data = each.value
}

resource "google_secret_manager_secret" "github_oauth" {
  for_each  = toset(["auth-github-id", "auth-github-secret"])
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# Cloud Run cannot start a revision whose secret has no version, so each hand-added secret
# starts with the placeholder "unconfigured", which the code treats as unset
# (pipeline/env.py, web/lib/auth.ts). Real values are added as newer versions by hand;
# Terraform never overwrites them.
resource "google_secret_manager_secret_version" "placeholder" {
  for_each = {
    github-token       = google_secret_manager_secret.github_token.id
    anthropic-api-key  = google_secret_manager_secret.anthropic_api_key.id
    auth-github-id     = google_secret_manager_secret.github_oauth["auth-github-id"].id
    auth-github-secret = google_secret_manager_secret.github_oauth["auth-github-secret"].id
  }
  secret      = each.value
  secret_data = "unconfigured"
}

# Collector config for the sidecars, mounted as a file.
resource "google_secret_manager_secret" "otel_config" {
  secret_id = "otel-collector-config"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "otel_config" {
  secret      = google_secret_manager_secret.otel_config.id
  secret_data = file("${path.module}/../observability/otel-collector-cloud.yaml")
}

locals {
  secret_readers = {
    "database_url:api"     = google_secret_manager_secret.database_url.id
    "database_url:poller"  = google_secret_manager_secret.database_url.id
    "database_url:migrate" = google_secret_manager_secret.database_url.id
    "github_token:poller"  = google_secret_manager_secret.github_token.id
    "anthropic:api"        = google_secret_manager_secret.anthropic_api_key.id
    "action:api"           = google_secret_manager_secret.generated["tpm-action-secret"].id
    "action:web"           = google_secret_manager_secret.generated["tpm-action-secret"].id
    "auth:web"             = google_secret_manager_secret.generated["auth-secret"].id
    "oauth_id:web"         = google_secret_manager_secret.github_oauth["auth-github-id"].id
    "oauth_secret:web"     = google_secret_manager_secret.github_oauth["auth-github-secret"].id
    "otel_config:api"      = google_secret_manager_secret.otel_config.id
    "otel_config:poller"   = google_secret_manager_secret.otel_config.id
    "otel_config:migrate"  = google_secret_manager_secret.otel_config.id
  }
}

resource "google_secret_manager_secret_iam_member" "readers" {
  for_each  = local.secret_readers
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.sa[split(":", each.key)[1]].member
}
