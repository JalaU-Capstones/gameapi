.DEFAULT_GOAL := help
.PHONY: help install dev run test test-cov lint format typecheck clean docker-up docker-down docker-logs docker-reset test-clean migrate migrate-create pre-commit pre-commit-install openapi-export openapi-check asyncapi-validate contracts-check monitoring-up monitoring-down monitoring-logs monitoring-clean

help:
	@echo "Comandos disponibles:"
	@echo "  make install     Instala dependencias con uv"
	@echo "  make dev         Ejecuta el servidor con recarga en caliente"
	@echo "  make run         Ejecuta el servidor en modo producción"
	@echo "  make test        Ejecuta los tests con pytest"
	@echo "  make test-cov    Ejecuta los tests con cobertura"
	@echo "  make lint        Analiza el código con ruff"
	@echo "  make format      Formatea el código con ruff"
	@echo "  make typecheck   Verifica tipos con mypy"
	@echo "  make openapi-export    Exporta el OpenAPI a .docs/contracts/openapi/openapi.json"
	@echo "  make openapi-check     Verifica que el OpenAPI commiteado esté sincronizado"
	@echo "  make asyncapi-validate Valida el contrato AsyncAPI"
	@echo "  make contracts-check   Verifica ambos contratos"
	@echo "  make clean       Limpia cachés y artefactos"
	@echo "  make docker-up   Levanta PostgreSQL y la API con docker-compose"
	@echo "  make docker-down Detiene los contenedores"
	@echo "  make monitoring-up     Inicia la API + PostgreSQL + Prometheus + Grafana"
	@echo "  make monitoring-down   Detiene la pila de monitoreo, conserva volúmenes"
	@echo "  make monitoring-logs   Sigue los logs de Prometheus y Grafana"
	@echo "  make monitoring-clean  Para la pila y borra solo volúmenes de monitoreo"
	@echo "  make migrate     Aplica las migraciones de Alembic"
	@echo "  make migrate-create Crea una migración de Alembic"

install:
	uv sync

dev:
	uv run python -m gameapi

run:
	uv run python -m gameapi

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist *.egg-info

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

docker-reset:
	docker compose down -v

# ---------------------------------------------------------------------------
# Observability stack (local only)
#
# The --env-file flag is mandatory: docker compose only auto-loads `.env`,
# and the overlay uses a fail-fast interpolation on GRAFANA_ADMIN_PASSWORD
# so a missing value aborts the command instead of starting Grafana with a
# default password. Keep the flag on every target that runs `docker compose`
# against the overlay.
# ---------------------------------------------------------------------------
COMPOSE_MONITORING = docker compose -f docker-compose.yml -f docker-compose.monitoring.yml --env-file .env.monitoring

monitoring-up: ## Start the API + PostgreSQL + Prometheus + Grafana + exporters
	$(COMPOSE_MONITORING) up -d

monitoring-down: ## Stop the monitoring stack, keep volumes
	$(COMPOSE_MONITORING) down

monitoring-logs: ## Tail logs from the monitoring containers
	$(COMPOSE_MONITORING) logs -f prometheus grafana

monitoring-clean: ## Stop the monitoring stack and wipe monitoring volumes only
	$(COMPOSE_MONITORING) down
	@for volume in gameapi_prometheus_data gameapi_grafana_data; do \
		if docker volume inspect "$$volume" >/dev/null 2>&1; then \
			docker volume rm "$$volume"; \
		fi; \
	done

test:
	uv run pytest -v

test-clean:
	docker ps -aq --filter "label=testcontainers" | xargs -r docker rm -f

test-cov:
	uv run coverage run -m pytest
	uv run coverage report --fail-under=93
	uv run coverage html
	@echo "HTML report: htmlcov/index.html"

pre-commit:
	uv run pre-commit run --all-files

pre-commit-install:
	uv run pre-commit install

openapi-export:
	uv run python scripts/export_openapi.py

openapi-check:
	uv run python scripts/export_openapi.py
	@if ! git diff --quiet .docs/contracts/openapi/openapi.json; then \
		echo "ERROR: openapi.json is out of date. Run 'make openapi-export' and commit the result."; \
		git diff .docs/contracts/openapi/openapi.json; \
		exit 1; \
	fi
	@echo "openapi.json is in sync."

asyncapi-validate:
	@if command -v asyncapi >/dev/null 2>&1; then \
		asyncapi validate .docs/contracts/asyncapi/asyncapi.json; \
	elif command -v npx >/dev/null 2>&1; then \
		npx --yes @asyncapi/cli validate .docs/contracts/asyncapi/asyncapi.json; \
	else \
		echo "Skipping AsyncAPI validation: neither 'asyncapi' nor 'npx' available."; \
	fi

contracts-check: openapi-check asyncapi-validate
	@echo "Both contracts are valid and up to date."

migrate:
	uv run alembic upgrade head

migrate-create:
	@read -p "Migration name: " name; \
	uv run alembic revision --autogenerate -m "$$name"
