.PHONY: setup dev test deploy teardown

# Create Kind cluster and deploy
setup:
	./scripts/setup-kind-cluster.sh

# Run locally without Kind
dev:
	docker-compose -f docker-compose.dev.yaml up

# Run tests
test:
	pytest tests/ -v
	cd frontend && npm test

# Deploy to Kind
deploy:
	./scripts/deploy.sh

# Teardown cluster
teardown:
	./scripts/teardown.sh

# Port-forward for local access
port-forward:
	kubectl port-forward svc/backend 8000:8000 -n financial-agent &
	kubectl port-forward svc/frontend 3000:3000 -n financial-agent &
	kubectl port-forward svc/chroma 8000:8000 -n financial-agent &
	kubectl port-forward svc/postgres 5432:5432 -n financial-agent &

# View logs
logs-backend:
	kubectl logs -f deployment/backend -n financial-agent

logs-frontend:
	kubectl logs -f deployment/frontend -n financial-agent

logs-chroma:
	kubectl logs -f deployment/chroma -n financial-agent

# Check status
status:
	kubectl get pods -n financial-agent
	kubectl get services -n financial-agent
	kubectl get ingress -n financial-agent