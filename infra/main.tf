locals {
  name = "tpm"
  apis = [
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "iamcredentials.googleapis.com", # keyless deploys from GitHub Actions
    "sts.googleapis.com",
  ]

  registry  = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
  app_image = "${local.registry}/app:${var.image_tag}" # one image for all Python services (Dockerfile)
  web_image = "${local.registry}/web:${var.image_tag}"
  # Same collector image as docker-compose.yml, run as a sidecar next to each Python service.
  otel_image = "otel/opentelemetry-collector-contrib:0.114.0"

  # Cloud Run's deterministic URLs, known before the services exist (web <-> API <-> GitHub
  # OAuth callback refer to each other).
  api_url = "https://${local.name}-api-${var.project_number}.${var.region}.run.app"
  web_url = "https://${var.web_service_name}-${var.project_number}.${var.region}.run.app"
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  repository_id = local.name
  location      = var.region
  format        = "DOCKER"
  description   = "Program Intelligence Platform container images"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 20
    }
  }

  depends_on = [google_project_service.apis]
}
