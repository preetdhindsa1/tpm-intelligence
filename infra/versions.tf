# Phase 1: plan only, never applied (README "Limitations"). State is local by default;
# a real deployment would use the commented GCS backend below.
terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # backend "gcs" {
  #   bucket = "<project>-tfstate"
  #   prefix = "tpm-intelligence"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
