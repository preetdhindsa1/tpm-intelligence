# Secrets live in Secret Manager, never in code or git (CLAUDE.md section 10).
# The GitHub token is added by hand after apply (read-only scope):
#   gcloud secrets versions add github-token --data-file=-
# Generated values (DB password, Redis auth) are written by Terraform, so the state file is
# sensitive and must live in a locked-down GCS bucket.

resource "google_secret_manager_secret" "github_token" {
  secret_id = "github-token"
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

resource "google_secret_manager_secret" "redis_url" {
  secret_id = "redis-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "redis_url" {
  secret      = google_secret_manager_secret.redis_url.id
  secret_data = "redis://:${google_redis_instance.cache.auth_string}@${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
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
    "database_url:worker"  = google_secret_manager_secret.database_url.id
    "database_url:poller"  = google_secret_manager_secret.database_url.id
    "database_url:migrate" = google_secret_manager_secret.database_url.id
    "redis_url:api"        = google_secret_manager_secret.redis_url.id
    "redis_url:worker"     = google_secret_manager_secret.redis_url.id
    "github_token:poller"  = google_secret_manager_secret.github_token.id
    "otel_config:api"      = google_secret_manager_secret.otel_config.id
    "otel_config:worker"   = google_secret_manager_secret.otel_config.id
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
