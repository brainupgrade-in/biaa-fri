# =============================================================================
# Makefile for Financial-Report Insight Agent
# =============================================================================

.PHONY: help setup deploy teardown status logs port-forward test lint

# Default target
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# =============================================================================
# Infrastructure
# =============================================================================

setup: ## Setup Kind cluster and deploy all services
	@chmod +x scripts/setup-infrastructure.sh
	@./scripts/setup-infrastructure.sh

setup-skip-build: ## Setup without building Docker images
	@chmod +x scripts/setup-infrastructure.sh
	@./scripts/setup-infrastructure.sh --skip-build

teardown: ## Tear down the entire infrastructure
	@chmod +x scripts/setup-infrastructure.sh
	@./scripts/setup-infrastructure.sh --teardown

# =============================================================================
# Deployment
# =============================================================================

deploy: ## Rebuild and redeploy application
	@chmod +x scripts/deploy.sh
	@./scripts/deploy.sh

# =============================================================================
# Operations
# =============================================================================

status: ## Show deployment status
	@chmod +x scripts/status.sh
	@./scripts/status.sh

logs: ## Show logs from all services (use: make logs-service SERVICE=backend)
	@chmod +x scripts/logs.sh
	@./scripts/logs.sh all

logs-backend: ## Show backend logs
	@chmod +x scripts/logs.sh
	@./scripts/logs.sh backend

logs-frontend: ## Show frontend logs
	@chmod +x scripts/logs.sh
	@./scripts/logs.sh frontend

logs-postgres: ## Show postgres logs
	@chmod +x scripts/logs.sh
	@./scripts/logs.sh postgres

port-forward: ## Set up port forwarding for local access
	@chmod +x scripts/port-forward.sh
	@./scripts/port-forward.sh

# =============================================================================
# Development
# =============================================================================

dev: ## Run locally with Docker Compose
	docker-compose -f docker-compose.dev.yaml up

dev-build: ## Build and run locally with Docker Compose
	docker-compose -f docker-compose.dev.yaml up --build

dev-down: ## Stop local development environment
	docker-compose -f docker-compose.dev.yaml down

# =============================================================================
# Testing
# =============================================================================

test: ## Run all tests
	pytest tests/ -v

test-integration: ## Run integration tests only
	pytest tests/integration/ -v

test-e2e: ## Run end-to-end tests only
	pytest tests/e2e/ -v

test-coverage: ## Run tests with coverage report
	pytest tests/ --cov=backend --cov-report=html --cov-report=xml

# =============================================================================
# Code Quality
# =============================================================================

lint: ## Run linter
	ruff check .

format: ## Format code
	ruff format .

typecheck: ## Run type checker
	mypy backend/

# =============================================================================
# Kubernetes Debugging
# =============================================================================

shell-backend: ## Open shell in backend pod
	kubectl exec -it deployment/backend -n financial-agent -- /bin/bash

shell-postgres: ## Open psql shell in postgres pod
	kubectl exec -it deployment/postgres -n financial-agent -- psql -U agent_user -d financial_agent

restart-backend: ## Restart backend deployment
	kubectl rollout restart deployment/backend -n financial-agent

restart-all: ## Restart all deployments
	kubectl rollout restart deployment -n financial-agent

# =============================================================================
# Database
# =============================================================================

db-migrate: ## Run database migrations
	kubectl exec -it deployment/backend -n financial-agent -- alembic upgrade head

db-status: ## Check database status
	kubectl exec -it deployment/postgres -n financial-agent -- pg_isready -U agent_user
