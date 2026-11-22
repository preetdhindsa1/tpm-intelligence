# Postgres, the source of truth (ADR-0002). No Redis in the cloud (ADR-0017): the API runs
# the worker in-process, so live updates need no broker.

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_database_instance" "db" {
  name             = "${local.name}-postgres"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = var.db_tier
    edition           = "ENTERPRISE"
    availability_type = "ZONAL" # demo scale; REGIONAL for the 99.5% availability SLO in production

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
      ipv4_enabled = true # reached only through the Cloud SQL connector (IAM-checked); no authorized networks
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  deletion_protection = true
  depends_on          = [google_project_service.apis]
}

resource "google_sql_database" "app" {
  name     = "tpm"
  instance = google_sql_database_instance.db.name
}

resource "google_sql_user" "app" {
  name     = "tpm"
  instance = google_sql_database_instance.db.name
  password = random_password.db.result
}
