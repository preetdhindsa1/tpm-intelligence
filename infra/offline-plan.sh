#!/bin/sh
# Offline Terraform plan: placeholder project, dummy token and local state in a scratch
# copy of the repository, so nothing in Google Cloud is contacted and the real GCS state
# (ADR-0017) is never touched. Used by `make tf-plan` and CI.
#   sh infra/offline-plan.sh [repo-root]
set -eu
SRC=${1:-.}
WORK=$(mktemp -d)
tar -C "$SRC" --exclude=./.git --exclude=./web --exclude=./infra/.terraform -cf - . | tar -C "$WORK" -xf -
cd "$WORK/infra"
cat > offline_override.tf <<'HCL'
terraform {
  backend "local" {}
}
HCL
terraform init -input=false >/dev/null
GOOGLE_OAUTH_ACCESS_TOKEN=offline-plan terraform plan -input=false -refresh=false -lock=false \
  -var project_id=tpm-demo-placeholder -var project_number=000000000000
