# Keyless deploys from GitHub Actions (ADR-0017): the deploy workflow exchanges its OIDC
# token for this service account through Workload Identity Federation. No JSON key exists.
# Only the main branch of var.github_repo can use it.

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == \"${var.github_repo}\" && assertion.ref == \"refs/heads/main\""
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  account_id   = "${local.name}-deployer"
  display_name = "GitHub Actions deployer (push images, run migrations, roll out)"
}

resource "google_service_account_iam_member" "deployer_from_github" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

resource "google_artifact_registry_repository_iam_member" "deployer_pushes" {
  repository = google_artifact_registry_repository.images.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deployer.member
}

# Update services and jobs, run the migration job.
resource "google_project_iam_member" "deployer_runs" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = google_service_account.deployer.member
}

# New revisions run as the workloads' own accounts, so the deployer may act as them.
resource "google_service_account_iam_member" "deployer_acts_as" {
  for_each           = toset(["api", "web", "poller", "migrate"])
  service_account_id = google_service_account.sa[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}
