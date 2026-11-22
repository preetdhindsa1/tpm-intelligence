.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck pytest test test-integration web-test evals backfill poll migrate up down logs tf-validate tf-plan

UV ?= uv
RELEASE ?=

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

evals: ## AI eval suite (no AI agents in phase 1)
	@echo "No evals yet: AI agents are out of scope for phase 1."

backfill: ## Load release data, e.g. make backfill RELEASE=v1.38
	@test -n "$(RELEASE)" || (echo "usage: make backfill RELEASE=v1.38" && exit 2)
	docker compose run --rm poller --release $(RELEASE) --backfill

poll: ## Incremental poll, e.g. make poll RELEASE=v1.38
	@test -n "$(RELEASE)" || (echo "usage: make poll RELEASE=v1.38" && exit 2)
	docker compose run --rm poller --release $(RELEASE)

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
	docker run --rm -v "$(CURDIR)":/work -w /work/infra -e GOOGLE_OAUTH_ACCESS_TOKEN=offline-plan \
	  hashicorp/terraform:1.10 plan -input=false -refresh=false -lock=false \
	  -var project_id=tpm-demo-placeholder -var project_number=000000000000
