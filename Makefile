.DEFAULT_GOAL := help
.PHONY: help install dev run test lint format typecheck clean docker-up docker-down

help:
	@echo "Comandos disponibles:"
	@echo "  make install     Instala dependencias con uv"
	@echo "  make dev         Ejecuta el servidor con recarga en caliente"
	@echo "  make run         Ejecuta el servidor en modo producción"
	@echo "  make test        Ejecuta los tests con pytest"
	@echo "  make lint        Analiza el código con ruff"
	@echo "  make format      Formatea el código con ruff"
	@echo "  make typecheck   Verifica tipos con mypy"
	@echo "  make clean       Limpia cachés y artefactos"
	@echo "  make docker-up   Levanta MongoDB y la API con docker-compose"
	@echo "  make docker-down Detiene los contenedores"

install:
	uv sync

dev:
	uv run uvicorn gameapi.main:app --reload --host $${APP_HOST:-0.0.0.0} --port $${APP_PORT:-8080}

run:
	uv run uvicorn gameapi.main:app --host $${APP_HOST:-0.0.0.0} --port $${APP_PORT:-8080}

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist *.egg-info

.PHONY: help install dev run test lint format typecheck clean docker-up docker-down docker-logs docker-reset

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

docker-reset:
	docker compose down -v

.PHONY: help install dev run test test-cov lint format typecheck pre-commit clean docker-up docker-down docker-logs docker-reset

test:
	uv run pytest -v

test-cov:
	uv run pytest --cov=gameapi --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"

pre-commit:
	uv run pre-commit run --all-files

pre-commit-install:
	uv run pre-commit install
