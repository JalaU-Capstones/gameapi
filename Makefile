.DEFAULT_GOAL := help
.PHONY: help install dev run test test-cov lint format typecheck clean docker-up docker-down docker-logs docker-reset test-clean migrate migrate-create pre-commit pre-commit-install

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
	@echo "  make docker-up   Levanta PostgreSQL y la API con docker-compose"
	@echo "  make docker-down Detiene los contenedores"
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

test:
	uv run pytest -v

test-clean:
	docker ps -aq --filter "label=testcontainers" | xargs -r docker rm -f

test-cov:
	uv run pytest --cov=gameapi --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"

pre-commit:
	uv run pre-commit run --all-files

pre-commit-install:
	uv run pre-commit install

migrate:
	uv run alembic upgrade head

migrate-create:
	@read -p "Migration name: " name; \
	uv run alembic revision --autogenerate -m "$$name"
