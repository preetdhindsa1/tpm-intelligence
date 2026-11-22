output "api_url" {
  description = "Public API URL."
  value       = google_cloud_run_v2_service.api.uri
}

output "web_url" {
  description = "Public dashboard URL (add it to cors_origins after the first apply)."
  value       = google_cloud_run_v2_service.web.uri
}

output "image_registry" {
  description = "Push app and web images here."
  value       = local.registry
}

output "cloud_sql_connection_name" {
  description = "For the Cloud SQL Auth Proxy when running backfills from a laptop."
  value       = google_sql_database_instance.db.connection_name
}
