# Cloud Run workloads (ADR-0007). One Python image (Dockerfile) with a different command
# per workload, matching docker-compose.yml. Each Python workload runs the OTel Collector
# as a sidecar on localhost:4317, exporting to Cloud Trace / Monitoring / Logging.

locals {
  common_env = {
    DEPLOY_ENV                  = "cloud"
    LOG_LEVEL                   = "INFO"
    QUEUE_BACKEND               = "pubsub"
    PUBSUB_PROJECT_ID           = var.project_id
    OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4317"
    OTEL_EXPORTER_OTLP_INSECURE = "true"
  }

  vpc_egress = {
    network    = google_compute_network.vpc.id
    subnetwork = google_compute_subnetwork.run.id
  }
}

# ---------------------------------------------------------------- API (FastAPI + SSE)

resource "google_cloud_run_v2_service" "api" {
  name                = "${local.name}-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.sa["api"].email
    timeout         = "3600s" # SSE streams stay open

    scaling {
      min_instance_count = 1 # keeps the in-process forecast cache warm (README: cold cache ~7 s)
      max_instance_count = 4
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = local.vpc_egress.network
        subnetwork = local.vpc_egress.subnetwork
      }
    }

    containers {
      name    = "api"
      image   = local.app_image
      command = ["python", "-m", "api.main"]

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle = false # recompute and SSE pushes happen outside requests
      }

      dynamic "env" {
        for_each = merge(local.common_env, {
          OTEL_SERVICE_NAME = "tpm-api"
          CORS_ORIGINS      = join(",", var.cors_origins)
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "REDIS_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.redis_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_api_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
        period_seconds    = 5
        failure_threshold = 24
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }

    containers {
      name  = "otel-collector"
      image = local.otel_image
      args  = ["--config=/etc/otelcol/config.yaml"]
      resources {
        limits = {
          cpu    = "0.5"
          memory = "256Mi"
        }
      }
      volume_mounts {
        name       = "otel-config"
        mount_path = "/etc/otelcol"
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.db.connection_name]
      }
    }
    volumes {
      name = "otel-config"
      secret {
        secret = google_secret_manager_secret.otel_config.secret_id
        items {
          version = "latest"
          path    = "config.yaml"
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.readers, google_secret_manager_secret_version.otel_config]
}

# ---------------------------------------------------------------- Web (Next.js)

resource "google_cloud_run_v2_service" "web" {
  name                = "${local.name}-web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.sa["web"].email

    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    containers {
      image = local.web_image
      ports {
        container_port = 3000
      }
      # Server-side rendering calls the API over HTTPS. The browser's SSE URL
      # (NEXT_PUBLIC_API_URL) is baked in at image build time.
      env {
        name  = "API_URL"
        value = google_cloud_run_v2_service.api.uri
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = var.public_access ? {
    api = google_cloud_run_v2_service.api.name
    web = google_cloud_run_v2_service.web.name
  } : {}
  name     = each.value
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------- Worker (Pub/Sub pull loop)
# A worker pool, not a service: pipeline/worker.py pulls continuously and serves no HTTP.

resource "google_cloud_run_v2_worker_pool" "worker" {
  name                = "${local.name}-worker"
  location            = var.region
  deletion_protection = false

  scaling {
    manual_instance_count = 1
  }

  template {
    service_account = google_service_account.sa["worker"].email

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = local.vpc_egress.network
        subnetwork = local.vpc_egress.subnetwork
      }
    }

    containers {
      name    = "worker"
      image   = local.app_image
      command = ["python", "-m", "pipeline.worker"]

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      dynamic "env" {
        for_each = merge(local.common_env, { OTEL_SERVICE_NAME = "tpm-worker" })
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "REDIS_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.redis_url.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }

    containers {
      name  = "otel-collector"
      image = local.otel_image
      args  = ["--config=/etc/otelcol/config.yaml"]
      volume_mounts {
        name       = "otel-config"
        mount_path = "/etc/otelcol"
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.db.connection_name]
      }
    }
    volumes {
      name = "otel-config"
      secret {
        secret = google_secret_manager_secret.otel_config.secret_id
        items {
          version = "latest"
          path    = "config.yaml"
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.readers, google_secret_manager_secret_version.otel_config]
}

# ---------------------------------------------------------------- Jobs: poller and migrations

resource "google_cloud_run_v2_job" "poller" {
  name                = "${local.name}-github-poller"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.sa["poller"].email
      timeout         = "1800s"
      max_retries     = 1 # exit 1 = a stream failed (collectors/github_poller/__main__.py)

      containers {
        name    = "poller"
        image   = local.app_image
        command = ["python", "-m", "collectors.github_poller"]
        args    = ["--release", var.poll_release]

        dynamic "env" {
          for_each = merge(local.common_env, { OTEL_SERVICE_NAME = "tpm-github-poller" })
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "GITHUB_TOKEN"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.github_token.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      containers {
        name  = "otel-collector"
        image = local.otel_image
        args  = ["--config=/etc/otelcol/config.yaml"]
        volume_mounts {
          name       = "otel-config"
          mount_path = "/etc/otelcol"
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.db.connection_name]
        }
      }
      volumes {
        name = "otel-config"
        secret {
          secret = google_secret_manager_secret.otel_config.secret_id
          items {
            version = "latest"
            path    = "config.yaml"
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.readers, google_secret_manager_secret_version.otel_config]
}

# Run before each deploy: gcloud run jobs execute tpm-migrate --wait
resource "google_cloud_run_v2_job" "migrate" {
  name                = "${local.name}-migrate"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.sa["migrate"].email
      timeout         = "600s"
      max_retries     = 0

      containers {
        image   = local.app_image
        command = ["alembic", "upgrade", "head"]
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.db.connection_name]
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.readers]
}
