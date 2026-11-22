#!/bin/sh
# One-time: the bucket that holds Terraform state (ADR-0017). State contains generated
# secrets, so the bucket is private, uniform-access and versioned.
set -eu
PROJECT=${1:?usage: bootstrap.sh <project-id> [region]}
REGION=${2:-us-central1}
BUCKET="gs://${PROJECT}-tfstate"
if gcloud storage buckets describe "$BUCKET" --project "$PROJECT" >/dev/null 2>&1; then
  echo "$BUCKET exists"
else
  gcloud storage buckets create "$BUCKET" --project "$PROJECT" --location "$REGION" \
    --uniform-bucket-level-access --public-access-prevention
  gcloud storage buckets update "$BUCKET" --versioning
fi
