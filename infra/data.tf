# Postgres (source of truth) and Redis (cache, live push): ADR-0002.

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

resource "google_redis_instance" "cache" {
  name               = "${local.name}-redis"
  tier               = "BASIC"
  memory_size_gb     = var.redis_memory_gb
  region             = var.region
  redis_version      = "REDIS_7_2"
  authorized_network = google_compute_network.vpc.id
  connect_mode       = "DIRECT_PEERING"
  auth_enabled       = true
  depends_on         = [google_project_service.apis]
}
