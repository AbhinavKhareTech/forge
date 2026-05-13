.PHONY: install install-all lint format test test-integration test-e2e test-security test-chaos clean docs docker docker-push helm-install helm-uninstall deploy setup sbom security-scan coverage

# ── Installation ──────────────────────────────────────────────
install:
	pip install -e ".[dev]"

install-all:
	pip install -e ".[all]"

# ── Code Quality ──────────────────────────────────────────────
lint:
	ruff check src tests
	ruff format --check src tests
	mypy src --show-error-codes
	bandit -r src/ -f json -o bandit-report.json || true

format:
	ruff format src tests
	ruff check --fix src tests

# ── Testing ───────────────────────────────────────────────────
test:
	pytest -v --cov=forge --cov-report=term-missing --cov-report=xml -n auto

test-integration:
	pytest -v -m integration

test-e2e:
	pytest -v -m e2e --headed

test-security:
	bandit -r src/
	pip-audit --format=json
	semgrep --config=auto src/

test-chaos:
	pytest -v -m chaos

test-all: test test-integration test-security

coverage:
	pytest --cov=forge --cov-report=html --cov-report=term-missing
	@echo "Open htmlcov/index.html for detailed coverage report"

# ── Documentation ───────────────────────────────────────────────
docs:
	mkdocs serve

docs-build:
	mkdocs build

docs-deploy:
	mike deploy --push --update-aliases $(VERSION) latest

# ── Docker ────────────────────────────────────────────────────
docker:
	docker build -t ahinsaai/forge:latest -f docker/Dockerfile .

docker-push:
	docker push ahinsaai/forge:latest

docker-run:
	docker-compose -f docker/docker-compose.yml up -d

docker-stop:
	docker-compose -f docker/docker-compose.yml down

# ── Kubernetes / Helm ───────────────────────────────────────────
helm-install:
	helm upgrade --install forge ./helm/forge --namespace forge --create-namespace

helm-uninstall:
	helm uninstall forge --namespace forge

helm-lint:
	helm lint ./helm/forge

# ── Security ──────────────────────────────────────────────────
security-scan:
	bandit -r src/ -f json -o bandit-report.json
	pip-audit --format=json -o pip-audit-report.json
	semgrep --config=auto --json --output=semgrep-report.json src/ || true

trivy-scan:
	trivy image ahinsaai/forge:latest
	trivy filesystem --scanners vuln,secret,config .

# ── SBOM ────────────────────────────────────────────────────────
sbom:
	syft packages dir:. -o spdx-json=sbom.spdx.json
	syft packages dir:. -o cyclonedx-json=sbom.cyclonedx.json

# ── Deployment ──────────────────────────────────────────────────
deploy:
	./scripts/deploy.sh production

setup:
	./scripts/setup-local.sh

# ── Cleanup ───────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache htmlcov dist *.egg-info .coverage coverage.xml
	rm -f bandit-report.json pip-audit-report.json semgrep-report.json sbom.*

# ── Development ───────────────────────────────────────────────
dev:
	FORGE_ENVIRONMENT=development FORGE_DEBUG=true uvicorn forge.api.server:app --reload --host 0.0.0.0 --port 8000

# ── Help ──────────────────────────────────────────────────────
help:
	@echo "Forge Development Commands"
	@echo "=========================="
	@echo "install          Install dev dependencies"
	@echo "install-all      Install all extras"
	@echo "lint             Run all linters and type checkers"
	@echo "format           Auto-format code"
	@echo "test             Run unit tests with coverage"
	@echo "test-integration Run integration tests"
	@echo "test-e2e         Run end-to-end tests"
	@echo "test-security    Run security scans"
	@echo "test-chaos       Run chaos engineering tests"
	@echo "coverage         Generate HTML coverage report"
	@echo "docs             Serve docs locally"
	@echo "docker           Build Docker image"
	@echo "docker-run       Run with docker-compose"
	@echo "helm-install     Install Helm chart"
	@echo "security-scan    Run all security scanners"
	@echo "sbom             Generate SBOM artifacts"
	@echo "clean            Remove build artifacts"
	@echo "dev              Run development server"
