output "api_url" {
  description = "Public API URL."
  value       = google_cloud_run_v2_service.api.uri
}

output "web_url" {
  description = "Public dashboard URL. GitHub OAuth callback: <web_url>/api/auth/callback/github"
  value       = local.web_url
}

output "image_registry" {
  description = "Push app and web images here."
  value       = local.registry
}

output "cloud_sql_connection_name" {
  description = "For the Cloud SQL Auth Proxy when running backfills from a laptop."
  value       = google_sql_database_instance.db.connection_name
}

output "workload_identity_provider" {
  description = "GitHub repository variable GCP_WIF_PROVIDER for the deploy workflow."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "GitHub repository variable GCP_DEPLOYER for the deploy workflow."
  value       = google_service_account.deployer.email
}

output "webhook_url" {
  description = "GitHub App webhook URL (append /github)."
  value       = "${local.webhook_url}/github"
}
