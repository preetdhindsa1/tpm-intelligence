#!/bin/sh
# First deployment of option B (ADR-0017) to Google Cloud. Run from the repository root:
#
#   sh infra/first-deploy.sh --yes [--with-local-secrets] [--seed-local-data]
#
# --yes                 required: creates billable resources (estimated ~$95-125/month)
# --with-local-secrets  copy GITHUB_TOKEN and ANTHROPIC_API_KEY from .env into Secret
#                       Manager (piped, never printed) if those secrets are still the
#                       placeholder
# --seed-local-data     copy the local Postgres database (public data only) into Cloud SQL
#                       once, so the site starts with v1.33-v1.38 instead of hours of
#                       backfill
#
# Safe to re-run: each step skips what is already done. Later deploys run from GitHub
# Actions (.github/workflows/deploy.yml).
set -eu

YES=0 SECRETS=0 SEED=0
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --with-local-secrets) SECRETS=1 ;;
    --seed-local-data) SEED=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done
[ "$YES" = 1 ] || { sed -n '2,17p' "$0"; echo "Refusing without --yes (this creates billable resources)." >&2; exit 2; }

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
[ -f infra/terraform.tfvars ] || { echo "infra/terraform.tfvars is missing (see the example)" >&2; exit 2; }
PROJECT=$(sed -n 's/^project_id *= *"\(.*\)"/\1/p' infra/terraform.tfvars)
NUMBER=$(sed -n 's/^project_number *= *"\(.*\)"/\1/p' infra/terraform.tfvars)
REGION=$(sed -n 's/^region *= *"\(.*\)"/\1/p' infra/terraform.tfvars)
REGION=${REGION:-us-central1}
REG="$REGION-docker.pkg.dev/$PROJECT/tpm"
API_URL="https://tpm-api-$NUMBER.$REGION.run.app"
WEB_URL="https://tpm-web-$NUMBER.$REGION.run.app"

step() { printf '\n==> %s\n' "$*"; }
tf() {
  docker run --rm -v "$ROOT":/work -w /work/infra -e TF_IN_AUTOMATION=1 \
    -e GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token)" hashicorp/terraform:1.10 "$@"
}

step "1/8 Terraform state bucket"
sh infra/bootstrap.sh "$PROJECT" "$REGION"
tf init -input=false -reconfigure >/dev/null

step "2/8 APIs and the image registry"
tf apply -input=false -auto-approve \
  -target=google_project_service.apis -target=google_artifact_registry_repository.images

step "3/8 Build and push the first images (linux/amd64)"
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet
TAG=$(sed -n 's/^image_tag *= *"\(.*\)"/\1/p' infra/terraform.tfvars)
TAG=${TAG:-bootstrap}
if gcloud artifacts docker images describe "$REG/app:$TAG" >/dev/null 2>&1; then
  echo "images :$TAG exist"
else
  docker buildx build --platform linux/amd64 -t "$REG/app:$TAG" --push .
  docker buildx build --platform linux/amd64 --build-arg NEXT_PUBLIC_API_URL="$API_URL" \
    -t "$REG/web:$TAG" --push web
fi

step "4/8 Everything else (Terraform apply)"
tf apply -input=false -auto-approve

placeholder() { [ "$(gcloud secrets versions access latest --secret "$1" --project "$PROJECT" 2>/dev/null)" = unconfigured ]; }
from_env() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -1; }

step "5/8 Hand-added secrets"
if [ "$SECRETS" = 1 ]; then
  for pair in github-token:GITHUB_TOKEN anthropic-api-key:ANTHROPIC_API_KEY; do
    secret=${pair%%:*} var=${pair#*:}
    if placeholder "$secret" && [ -n "$(from_env "$var")" ]; then
      from_env "$var" | tr -d '\n' | gcloud secrets versions add "$secret" --data-file=- --project "$PROJECT" >/dev/null
      echo "$secret: copied from .env"
    else
      echo "$secret: already set (or not in .env)"
    fi
  done
else
  echo "skipped (--with-local-secrets not given)"
fi
for s in github-token anthropic-api-key auth-github-id auth-github-secret; do
  placeholder "$s" && echo "still a placeholder: $s"
done

step "6/8 Data"
SEED_BUCKET="gs://$PROJECT-seed"
if [ "$SEED" = 1 ]; then
  if gcloud storage objects describe "$SEED_BUCKET/SEEDED" >/dev/null 2>&1; then
    echo "already seeded"
  else
    gcloud storage buckets describe "$SEED_BUCKET" >/dev/null 2>&1 || \
      gcloud storage buckets create "$SEED_BUCKET" --project "$PROJECT" --location "$REGION" \
        --uniform-bucket-level-access --public-access-prevention
    DUMP=$(mktemp -d)/tpm.sql.gz
    docker compose exec -T postgres pg_dump -U tpm -d tpm --no-owner --no-privileges | gzip > "$DUMP"
    gcloud storage cp "$DUMP" "$SEED_BUCKET/tpm.sql.gz"
    SQL_SA=$(gcloud sql instances describe tpm-postgres --project "$PROJECT" --format='value(serviceAccountEmailAddress)')
    gcloud storage buckets add-iam-policy-binding "$SEED_BUCKET" \
      --member "serviceAccount:$SQL_SA" --role roles/storage.objectViewer >/dev/null
    gcloud sql import sql tpm-postgres "$SEED_BUCKET/tpm.sql.gz" --database tpm --user tpm \
      --project "$PROJECT" --quiet
    gcloud storage rm "$SEED_BUCKET/tpm.sql.gz"
    echo "seeded $(date -u +%FT%TZ)" | gcloud storage cp - "$SEED_BUCKET/SEEDED"
  fi
else
  echo "skipped (--seed-local-data not given); run backfills instead"
fi

step "7/8 Migrations"
gcloud run jobs execute tpm-migrate --region "$REGION" --project "$PROJECT" --wait

step "8/8 Smoke test"
curl -fsS --retry 20 --retry-delay 15 --retry-all-errors "$API_URL/healthz" && echo
curl -fsS "$API_URL/me" && echo
curl -fsS -o /dev/null -w "web: HTTP %{http_code}\n" --retry 5 --retry-delay 10 "$WEB_URL/"

cat <<EOF

Done. Live site: $WEB_URL   API: $API_URL
Next (by hand):
  - GitHub OAuth app, callback $WEB_URL/api/auth/callback/github; then
      printf %s "\$ID"     | gcloud secrets versions add auth-github-id --data-file=-
      printf %s "\$SECRET" | gcloud secrets versions add auth-github-secret --data-file=-
    and redeploy web (or wait for the next deploy) to pick them up.
  - Repository variables (GitHub -> Settings -> Variables) for keyless deploys:
      GCP_PROJECT_ID=$PROJECT GCP_PROJECT_NUMBER=$NUMBER GCP_REGION=$REGION
      GCP_WIF_PROVIDER=$(tf output -raw workload_identity_provider)
      GCP_DEPLOYER=$(tf output -raw deployer_service_account)
  - Budget alert on the billing account (console: Billing -> Budgets & alerts).
EOF
