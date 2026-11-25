.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck pytest test test-integration web-test evals backfill poll jira-sync notes-sync slack-sync migrate up down logs tf-validate tf-plan langfuse-up langfuse-down ai-smoke evals-live suggest-links sim-validate sim-calibrate snapshot score-snapshots

UV ?= uv
RELEASE ?=
TEAM ?= kubernetes

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: ## Install Python deps (incl. dev) into .venv
	$(UV) sync --frozen

lint: ## ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format: ## Auto-fix lint and formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck: ## mypy (strict for engine/, linker/, verify/)
	$(UV) run mypy

pytest: ## Unit tests (no external services)
	$(UV) run pytest -m "not integration"

test: lint typecheck pytest ## ruff + mypy + pytest

test-integration: ## Tests that need docker compose services running
	$(UV) run pytest -m integration

web-test: ## Web: lint, typecheck, unit tests, build (runs in Node 20 via Docker)
	docker run --rm -v "$(CURDIR)/web":/app -w /app node:20-alpine sh -c "npm ci --no-audit --no-fund && npm run lint && npm run typecheck && npm test && npm run build"

evals: ## Eval suites (fact checker, linking); saves docs/results/evals-*.json
	$(UV) run python -m evals.run_evals

backfill: ## Load release data, e.g. make backfill TEAM=kubernetes RELEASE=v1.38 (TEAM=kafka: PRs only)
	@test -n "$(RELEASE)" || (echo "usage: make backfill TEAM=kubernetes RELEASE=v1.38" && exit 2)
	docker compose run --rm poller --team $(TEAM) --release $(RELEASE) --backfill

poll: ## Incremental poll, e.g. make poll TEAM=kubernetes RELEASE=v1.38
	@test -n "$(RELEASE)" || (echo "usage: make poll TEAM=kubernetes RELEASE=v1.38" && exit 2)
	docker compose run --rm poller --team $(TEAM) --release $(RELEASE)

slack-sync: ## Slack channels a team lists (needs SLACK_BOT_TOKEN), e.g. make slack-sync TEAM=tpm-intelligence
	$(UV) run python -m collectors.slack --team $(TEAM)

notes-sync: ## Public meeting notes for a team (ADR-0030), e.g. make notes-sync TEAM=kubernetes
	$(UV) run python -m collectors.notes --team $(or $(TEAM),kubernetes)

jira-sync: ## Jira plan for a Jira team (anonymous, slow on purpose), e.g. make jira-sync TEAM=kafka RELEASE=4.4.0
	@test -n "$(RELEASE)" || (echo "usage: make jira-sync TEAM=kafka RELEASE=4.4.0" && exit 2)
	docker compose run --rm jira --team $(TEAM) $(foreach r,$(RELEASE),--release $(r)) $(if $(BACKFILL),--backfill,)

migrate: ## Apply DB migrations
	$(UV) run alembic upgrade head

up: ## Start the local stack
	docker compose up -d --build

down: ## Stop the local stack
	docker compose down

logs: ## Tail service logs
	docker compose logs -f api worker otel-collector

TERRAFORM = docker run --rm -v "$(CURDIR)":/work -w /work/infra hashicorp/terraform:1.10

tf-validate: ## Terraform fmt check + validate (Docker; no cloud credentials)
	$(TERRAFORM) fmt -check -recursive
	$(TERRAFORM) init -backend=false -input=false >/dev/null
	$(TERRAFORM) validate

tf-plan: tf-validate ## Offline plan with a placeholder project and dummy token: nothing is contacted or applied
	docker run --rm -v "$(CURDIR)":/src:ro --entrypoint sh hashicorp/terraform:1.10 /src/infra/offline-plan.sh /src

tf-real-plan: ## Plan against tpm-intelligence (reads the cloud and GCS state; changes nothing)
	docker run --rm -v "$(CURDIR)":/work -w /work/infra -e GOOGLE_OAUTH_ACCESS_TOKEN="$$(gcloud auth print-access-token)" hashicorp/terraform:1.10 init -input=false -reconfigure
	docker run --rm -v "$(CURDIR)":/work -w /work/infra -e GOOGLE_OAUTH_ACCESS_TOKEN="$$(gcloud auth print-access-token)" hashicorp/terraform:1.10 plan -input=false -out=main.tfplan

LANGFUSE = docker compose -p tpm-langfuse --env-file .env -f observability/langfuse/docker-compose.yml -f observability/langfuse/compose.override.yml

langfuse-up: ## Start self-hosted Langfuse (LLM traces) on http://localhost:3001
	$(LANGFUSE) up -d

langfuse-down: ## Stop Langfuse (data kept in its volumes)
	$(LANGFUSE) down

evals-live: ## Paid agent evals (risk analyst ~$0.03, VP summary ~$0.40); SUITE=all|risk_analyst|vp_summary|link_suggester|raid_extractor
	docker compose build -q api
	docker run --rm --network tpm-intelligence_default --env-file .env \
	  -e DATABASE_URL=postgresql+psycopg://tpm:tpm@postgres:5432/tpm \
	  -e OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317 -e OTEL_EXPORTER_OTLP_INSECURE=true \
	  -v "$(CURDIR)/docs/results:/app/docs/results" tpm-intelligence-api python -m evals.agents --suite $(or $(SUITE),all)

sim-validate: ## Fit the simulator on earlier releases, replay v1.37 and v1.38 (~3 min, no AI)
	$(UV) run python scripts/validate_simulator.py

sim-calibrate: ## Fit the simulator for RELEASE and store it for the API (~2 min, no AI)
	$(UV) run python scripts/calibrate_simulator.py --release $(or $(RELEASE),v1.38)

snapshot: ## Record today's forecast of the current release (append-only; ADR-0015)
	$(UV) run python scripts/snapshot_forecasts.py $(if $(RELEASE),--release $(RELEASE),)

score-snapshots: ## Score a finished release on its recorded forecasts, e.g. RELEASE=v1.39
	@test -n "$(RELEASE)" || (echo "usage: make score-snapshots RELEASE=v1.39" && exit 2)
	$(UV) run python scripts/score_snapshots.py --release $(RELEASE)

suggest-links: ## Paid AI link suggestions for unlinked PRs (~$0.0004 each); RELEASE=v1.38 LIMIT=
	docker compose build -q api
	docker compose run --rm --no-deps -e OTEL_SERVICE_NAME=tpm-link-suggester api \
	  python scripts/suggest_links.py --release $(or $(RELEASE),v1.38) $(if $(LIMIT),--limit $(LIMIT),)

ai-smoke: ## One real Claude call on #6395 facts, fact-checked (costs < $0.01; needs ANTHROPIC_API_KEY)
	docker compose run --rm --no-deps -e OTEL_SERVICE_NAME=tpm-ai-smoke api python scripts/ai_smoke.py
