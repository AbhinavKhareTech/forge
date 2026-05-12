.PHONY: install lint format test clean docs docker deploy

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests
	mypy src

format:
	ruff format src tests
	ruff check --fix src tests

test:
	pytest -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache htmlcov dist *.egg-info

docs:
	mkdocs serve

docker:
	docker build -t ahinsaai/forge:latest -f docker/Dockerfile .

docker-run:
	docker-compose -f docker/docker-compose.yml up -d

docker-stop:
	docker-compose -f docker/docker-compose.yml down

helm-install:
	helm upgrade --install forge ./helm/forge --namespace forge --create-namespace

helm-uninstall:
	helm uninstall forge --namespace forge

deploy:
	./scripts/deploy.sh production

setup:
	./scripts/setup-local.sh
