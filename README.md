# GameAPI

REST API para gestión de usuarios y partidas de Tic-Tac-Toe.

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![codecov](https://codecov.io/gh/JalaU-Capstones/gameapi/branch/main/graph/badge.svg)](https://codecov.io/gh/JalaU-Capstones/gameapi)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Tests](https://img.shields.io/badge/tests-55%20passed-success.svg)](#pruebas)

**Stack:** Python 3.12+ · FastAPI · PostgreSQL 16 · SQLAlchemy 2.0 async · Pydantic v2 · JWT · uv · Docker

---

## Tabla de contenidos

- [Características](#características)
- [Requisitos](#requisitos)
- [Clonación](#clonación)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Ejecución](#ejecución)
- [Endpoints](#endpoints)
- [Pruebas](#pruebas)
- [Docker](#docker)
- [Arquitectura](#arquitectura)
- [Convenciones de nomenclatura](#convenciones-de-nomenclatura)
- [Seguridad](#seguridad)
- [Licencia](#licencia)

---

## Características

- Registro y gestión de usuarios (nombre, email, contraseña).
- Autenticación con JWT y contraseñas hasheadas con bcrypt.
- CRUD completo de partidas (gameplays) con estado en JSONB flexible.
- Endpoints protegidos por token y validación de propiedad.
- Validación de datos con Pydantic v2.
- Documentación interactiva con Swagger UI y ReDoc.
- Tests automatizados con pytest + httpx sobre PostgreSQL, con modo local en Docker via `testcontainers` y modo CI con servicio nativo.
- ORM async con SQLAlchemy 2.0 y PostgreSQL como base de datos principal.
- Dockerizado con healthchecks y multi-stage build.

---

## Requisitos

Antes de instalar, asegúrate de tener:

| Herramienta | Versión mínima | Instalación |
|---|---|---|
| **Python** | 3.12+ | <https://www.python.org/downloads/> |
| **uv** | 0.4+ | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Git** | 2.30+ | <https://git-scm.com/downloads> |
| **PostgreSQL** | 16 | <https://www.postgresql.org/download/> |
| **Docker** + **Compose** | 24+ / v2 (opcional) | <https://docs.docker.com/get-docker/> |

> **Recomendado:** usa Docker para levantar PostgreSQL y la API sin instalar nada más. Si prefieres desarrollo local, instala PostgreSQL 16.

---

## Clonación

```bash
git clone https://github.com/JalaU-Capstones/gameapi.git
cd gameapi
```

---

## Instalación

**1. Sincronizar dependencias** (crea `.venv` automáticamente):

```bash
uv sync
```

**2. Crear el archivo de entorno** a partir del ejemplo:

```bash
cp .env.example .env
```

**3. Editar `.env`** si necesitas cambiar la URI de PostgreSQL, el `JWT_SECRET_KEY` o los orígenes CORS.

---

## Configuración

Todas las variables se leen desde `.env` (ver `.env.example`):

| Variable | Descripción | Default |
|---|---|---|
| `POSTGRES_URI` | URI de PostgreSQL para SQLAlchemy async | `postgresql+asyncpg://gameapi:gameapi@localhost:5432/gameapi` |
| `POSTGRES_USER` | Usuario de PostgreSQL (para Docker Compose) | `gameapi` |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL (para Docker Compose) | `gameapi` |
| `POSTGRES_DB` | Nombre de la base de datos PostgreSQL | `gameapi` |
| `POSTGRES_PORT` | Puerto host de PostgreSQL (para Docker Compose) | `5432` |
| `JWT_SECRET_KEY` | Clave secreta para firmar JWT (mín. 32 caracteres) | *(requerido)* |
| `JWT_ALGORITHM` | Algoritmo de firma | `HS256` |
| `JWT_ISSUER` | Emisor del token | `GameAPI` |
| `JWT_AUDIENCE` | Audiencia del token | `GameAPI` |
| `JWT_EXPIRE_MINUTES` | Expiración del token en minutos | `60` |
| `APP_ENV` | Entorno (`development` / `staging` / `production`) | `development` |
| `APP_HOST` | Host de escucha | `0.0.0.0` |
| `APP_PORT` | Puerto de escucha | `8080` |
| `CORS_ORIGINS` | Orígenes permitidos (coma-separados o `*`) | `*` |

---

## Ejecución

### Opción 1: Local (con PostgreSQL corriendo aparte)

```bash
# Levantar PostgreSQL con Docker
docker run -d --name game-postgres -p 5432:5432 \
  -e POSTGRES_USER=gameapi \
  -e POSTGRES_PASSWORD=gameapi \
  -e POSTGRES_DB=gameapi \
  postgres:16-alpine

# Aplicar migraciones
uv run alembic upgrade head

# Arrancar la API en modo desarrollo
make dev
```

### Opción 2: Docker Compose (API + PostgreSQL)

```bash
make docker-up
```

### Migraciones con Alembic

La variable `POSTGRES_URI` debe apuntar a una instancia de PostgreSQL en ejecución antes de aplicar las migraciones.

Con PostgreSQL disponible, aplica el esquema inicial con:

```bash
uv run alembic upgrade head
```

Para revertir una revisión:

```bash
uv run alembic downgrade -1
```

Para crear una migración a partir de cambios en los modelos:

```bash
uv run alembic revision --autogenerate -m "description"
```

Las migraciones versionadas se almacenan en `migrations/versions/`.

### URLs

| Recurso | URL |
|---|---|
| API | <http://localhost:8080> |
| Swagger UI | <http://localhost:8080/docs> |
| ReDoc | <http://localhost:8080/redoc> |
| OpenAPI JSON | <http://localhost:8080/openapi.json> |
| Health check | <http://localhost:8080/health> |

---

## Endpoints

### Users

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `POST` | `/api/users` | ❌ | Registrar usuario |
| `GET` | `/api/users` | ❌ | Listar usuarios |
| `GET` | `/api/users/{id}` | ❌ | Obtener un usuario |
| `PUT` | `/api/users/{id}` | ✅ | Actualizar **tu propia** cuenta |
| `DELETE` | `/api/users/{id}` | ✅ | Eliminar **tu propia** cuenta |
| `POST` | `/api/users/login` | ❌ | Login (devuelve JWT) |

### Gameplays

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/api/gameplays` | ❌ | Listar todas las partidas |
| `GET` | `/api/gameplays/my-gameplays` | ✅ | Partidas del usuario autenticado |
| `GET` | `/api/gameplays/player/{id}` | ❌ | Partidas de un jugador |
| `GET` | `/api/gameplays/{id}` | ❌ | Obtener una partida |
| `POST` | `/api/gameplays` | ✅ | Crear partida (host = tú) |
| `PUT` | `/api/gameplays/{id}` | ✅ | Actualizar (solo participantes) |
| `DELETE` | `/api/gameplays/{id}` | ✅ | Eliminar (solo host) |

### Ejemplos

**Registrar usuario:**

```bash
curl -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Sandra Dee","email":"sandra@mail.com","password":"password123"}'
```

**Login y guardar token (bash):**

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/api/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sandra@mail.com","password":"password123"}' | jq -r .token)
```

**Login (fish shell):**

```fish
set TOKEN (curl -s -X POST http://localhost:8080/api/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sandra@mail.com","password":"password123"}' | jq -r .token)
```

**Crear partida:**

```bash
curl -X POST http://localhost:8080/api/gameplays \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "currentPositions": "{\"board\": [[0,0,0],[0,0,0],[0,0,0]], \"lastMove\": null}",
    "hostPlayer": "USER_ID",
    "playerTurn": "USER_ID"
  }'
```

**Colección Postman:** importa `GameAPI.postman_collection.json` (incluye login automático que guarda el token).

---

## Pruebas

```bash
make test
```

Salida esperada:

```
55 passed in ~13s
Required test coverage of 85.0% reached. Total coverage: 87.96%
```

Los tests usan **PostgreSQL** de dos formas según el entorno:

- **Local:** levantan un contenedor efímero con `testcontainers[postgresql]`.
  Requieren Docker corriendo. La primera ejecución descarga la imagen
  `postgres:16-alpine` (~100 MB).
- **CI:** usan un servicio PostgreSQL nativo del runner, configurado vía la
  variable de entorno `TEST_POSTGRES_URI`. Esto evita la sobrecarga de
  Docker-in-Docker y hace los pipelines más rápidos y fiables.

### Cobertura

**Umbral mínimo:** 85% (configurado en `pyproject.toml` → `[tool.coverage.report] fail_under`).

**Cobertura actual:** 87.96% (537 statements, 86 branches).

| Archivo | Tests | Cobertura | Qué cubre |
|---|---|---|---|
| `tests/test_security.py` | 4 | 100% | Hashing bcrypt, JWT create/decode, token manipulado. |
| `tests/test_health.py` | 1 | 78% (`main.py`) | Endpoint `/health` con PostgreSQL disponible. |
| `tests/test_users.py` | 14 | 88% | Registro, duplicado, validación, login, CRUD con permisos. |
| `tests/test_gameplays.py` | 14 | 83% | CRUD, validación JSON, permisos host/guest. |
| `tests/test_edge_cases.py` | 22 | — | Edge cases: UUID validation, session lifecycle, auth malformado, guest inexistente, jugadores ajenos, validación de dominio. |

**Reporte HTML** (local, tras `make test`):

```bash
open htmlcov/index.html
```

**Reporte XML** (generado por pytest-cov para CI): `coverage.xml` → subido a Codecov en cada push a `main`.

**Módulos con menor cobertura**:

- `main.py` (78%): `lifespan` real y algunos branches del exception handler.
- `api/v1/gameplays.py` (83%): branches secundarios del update / list.

### Calidad de código

```bash
make lint        # ruff check
make format      # ruff format
make typecheck   # mypy strict
```

Pre-commit ejecuta automáticamente todos los checks antes de cada `git commit`:

```bash
make pre-commit-install   # instala los hooks (una sola vez)
make pre-commit           # corre todos los hooks manualmente
```

Hooks configurados: `ruff`, `ruff-format`, `mypy`, `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-added-large-files`, `check-merge-conflict`, `mixed-line-ending`.

### Integración continua

**GitHub Actions** (`.github/workflows/ci.yml`) — 3 jobs:

- `quality`: ruff + mypy.
- `test`: matriz Python 3.12 / 3.13 con cobertura, contra un servicio PostgreSQL 16.
- `docker`: build de la imagen + smoke test con PostgreSQL en red dedicada.

**GitLab CI** (`.gitlab-ci.yml`) — mismo flujo, con PostgreSQL 16 provisto como
`services:` nativo y cacheando solo `$UV_CACHE_DIR`.

**Dependabot** (`.github/dependabot.yml`) — PR semanal para actualizar `uv.lock` y GitHub Actions.

---

## Docker

```bash
make docker-up     # construir y levantar (postgres + api)
make docker-logs   # ver logs en vivo
make docker-down   # detener (conserva volúmenes)
make docker-reset  # detener y borrar datos
```

Detalles:

- Imagen de la API: multi-stage build (`ghcr.io/astral-sh/uv` + `python:3.12-slim-bookworm`).
- Usuario no-root en el contenedor.
- Healthchecks reales para PostgreSQL y la API.
- La API espera a que PostgreSQL esté `healthy` antes de arrancar.

---

## Arquitectura

```
gameapi/
├── src/gameapi/
│   ├── core/            # Config, seguridad (JWT + bcrypt)
│   ├── db/              # SQLAlchemy ORM + session management
│   ├── repositories/    # Data access layer (queries SQLAlchemy)
│   ├── schemas/         # Contratos de API (camelCase, validación)
│   ├── services/        # Lógica de negocio async, errores de dominio
│   ├── api/             # Routers FastAPI + dependencias (auth, DI)
│   └── main.py          # App FastAPI, lifespan, CORS, exception handlers
├── migrations/          # Migraciones Alembic
├── tests/               # pytest + httpx + PostgreSQL (local/CI dual-mode)
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

Flujo de una request:

```
HTTP → Router (api/v1) → Deps (auth, DI) → Service → Repository → SQLAlchemy → PostgreSQL
                              ↑
                              └── Security (JWT)
```

---

## Convenciones de nomenclatura

El proyecto mantiene **dos capas con estilos distintos** de forma deliberada:

| Capa | Convención | Motivo |
|---|---|---|
| Python interno (`db/`, `repositories/`, `services/`, `core/`) | `snake_case` | PEP 8 — estilo idiomático de Python |
| API pública (JSON entrada/salida) | `camelCase` | Compatibilidad con clientes existentes (frontend, Postman) |

La conversión es **automática** vía `pydantic.alias_generators.to_camel` en `schemas/base.py::ApiModel`.

### Tabla de mapeo

**Usuarios:**

| Python | JSON |
|---|---|
| `id` | `id` |
| `name` | `name` |
| `email` | `email` |
| `register_date` | `registerDate` |

**Partidas:**

| Python | JSON |
|---|---|
| `id` | `id` |
| `current_positions` | `currentPositions` |
| `host_player` | `hostPlayer` |
| `guest_player` | `guestPlayer` |
| `player_turn` | `playerTurn` |
| `match_result` | `matchResult` |
| `created_date` | `createdDate` |
| `updated_date` | `updatedDate` |

### Reglas para contribuir

1. **Modelos de dominio y servicios** → siempre `snake_case`.
2. **Schemas de API** → declarar en `snake_case`; el alias `camelCase` se genera solo.
3. **Nunca** exponer los modelos ORM directamente en la API; siempre traducir a schemas Pydantic.
4. Al agregar un endpoint, exponer el **schema** (nunca el `*Document`).
5. Antes de commitear: `make format && make lint && make typecheck && make test`.

---

## Seguridad

- Contraseñas hasheadas con **bcrypt** (con pre-hash SHA-256 para soportar passwords largas).
- Tokens JWT firmados con **HS256**; validación de `iss`, `aud`, `exp`, `iat`, `jti`.
- Validación de email único (constraint `UNIQUE` en PostgreSQL).
- Endpoints protegidos con `HTTPBearer`.
- Ownership check: un usuario solo puede modificar/eliminar sus propios recursos.
- CORS configurable por entorno.
- `JWT_SECRET_KEY` mínimo 32 caracteres (validado en el arranque).

---

## Licencia

Este proyecto está bajo la **GNU General Public License v3.0**.

Copyright (C) 2026 Diego Alejandro Botina.

Ver el archivo [`LICENSE`](./LICENSE) para el texto completo.
