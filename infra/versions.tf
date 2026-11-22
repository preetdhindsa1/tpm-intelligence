# State lives in a GCS bucket (versioned, uniform access, created once by
# infra/bootstrap.sh). CI's offline plan runs with -backend=false.
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

  backend "gcs" {
    bucket = "tpm-intelligence-tfstate"
    prefix = "tpm-intelligence"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
