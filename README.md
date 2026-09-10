# GameAPI

REST API para gestión de usuarios y partidas de Tic-Tac-Toe.

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Tests](https://img.shields.io/badge/tests-33%20passed-success.svg)](#pruebas)

**Stack:** Python 3.12+ · FastAPI · MongoDB (Motor) · Pydantic v2 · JWT · uv · Docker

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
- CRUD completo de partidas (gameplays) con estado en JSON flexible.
- Endpoints protegidos por token y validación de propiedad.
- Validación de datos con Pydantic v2.
- Documentación interactiva con Swagger UI y ReDoc.
- Tests automatizados con pytest + httpx + mongomock-motor (sin MongoDB real).
- Dockerizado con healthchecks y multi-stage build.

---

## Requisitos

Antes de instalar, asegúrate de tener:

| Herramienta | Versión mínima | Instalación |
|---|---|---|
| **Python** | 3.12+ | <https://www.python.org/downloads/> |
| **uv** | 0.4+ | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Git** | 2.30+ | <https://git-scm.com/downloads> |
| **MongoDB** | 7.0 (opcional si usas Docker) | <https://www.mongodb.com/try/download/community> |
| **Docker** + **Compose** | 24+ / v2 (opcional) | <https://docs.docker.com/get-docker/> |

> **Recomendado:** usa Docker para levantar MongoDB y la API sin instalar nada más. Si prefieres desarrollo local, instala MongoDB community o usa [MongoDB Atlas](https://www.mongodb.com/atlas) (cloud gratuito).

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

**3. Editar `.env`** si necesitas cambiar la cadena de conexión a MongoDB, el `JWT_SECRET_KEY` o los orígenes CORS.

---

## Configuración

Todas las variables se leen desde `.env` (ver `.env.example`):

| Variable | Descripción | Default |
|---|---|---|
| `MONGO_CONNECTION_STRING` | URI de MongoDB | `mongodb://localhost:27017` |
| `MONGO_DATABASE_NAME` | Nombre de la base de datos | `GameDB` |
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

### Opción 1: Local (con MongoDB corriendo aparte)

```bash
# Levantar solo MongoDB con Docker
docker run -d --name game-mongodb -p 27017:27017 mongo:7.0

# Arrancar la API en modo desarrollo (con hot-reload)
make dev
```

### Opción 2: Docker Compose (API + MongoDB)

```bash
make docker-up
```

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
33 passed in 9.52s
```

Los tests usan `mongomock-motor`, así que **no necesitan MongoDB real** ni levantarlo con Docker.

### Cobertura

- **`tests/test_security.py`** (4): hashing bcrypt, JWT create/decode, token manipulado.
- **`tests/test_health.py`** (1): endpoint `/health` con DB mockeada.
- **`tests/test_users.py`** (14): registro, duplicado, validación, login, CRUD con permisos.
- **`tests/test_gameplays.py`** (14): CRUD, validación JSON, permisos host/guest.

### Calidad de código

```bash
make lint        # ruff check
make format      # ruff format
make typecheck   # mypy strict
```

---

## Docker

```bash
make docker-up     # construir y levantar (mongo + api)
make docker-logs   # ver logs en vivo
make docker-down   # detener (conserva volúmenes)
make docker-reset  # detener y borrar datos
```

Detalles:

- Imagen de la API: multi-stage build (`ghcr.io/astral-sh/uv` + `python:3.12-slim-bookworm`).
- Usuario no-root en el contenedor.
- Healthchecks reales para MongoDB y la API.
- La API espera a que Mongo esté `healthy` antes de arrancar.

---

## Arquitectura

```
gameapi/
├── src/gameapi/
│   ├── core/            # Config, conexión Mongo, seguridad (JWT + bcrypt)
│   ├── models/          # Documentos de MongoDB (snake_case, ObjectId)
│   ├── schemas/         # Contratos de API (camelCase, validación)
│   ├── services/        # Lógica de negocio async, errores de dominio
│   ├── api/             # Routers FastAPI + dependencias (auth, DI)
│   └── main.py          # App FastAPI, lifespan, CORS, exception handlers
├── tests/               # pytest + httpx + mongomock
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

Flujo de una request:

```
HTTP → Router (api/v1) → Deps (auth, DI) → Service → Model → MongoDB
                              ↑
                              └── Security (JWT)
```

---

## Convenciones de nomenclatura

El proyecto mantiene **dos capas con estilos distintos** de forma deliberada:

| Capa | Convención | Motivo |
|---|---|---|
| Python interno (`models/`, `services/`, `core/`) | `snake_case` | PEP 8 — estilo idiomático de Python |
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
3. **Nunca** acceder al diccionario Mongo con claves `camelCase`.
4. Al agregar un endpoint, exponer el **schema** (nunca el `*Document`).
5. Antes de commitear: `make format && make lint && make typecheck && make test`.

---

## Seguridad

- Contraseñas hasheadas con **bcrypt** (con pre-hash SHA-256 para soportar passwords largas).
- Tokens JWT firmados con **HS256**; validación de `iss`, `aud`, `exp`, `iat`, `jti`.
- Validación de email único (índice único en MongoDB).
- Endpoints protegidos con `HTTPBearer`.
- Ownership check: un usuario solo puede modificar/eliminar sus propios recursos.
- CORS configurable por entorno.
- `JWT_SECRET_KEY` mínimo 32 caracteres (validado en el arranque).

---

## Licencia

Este proyecto está bajo la **GNU General Public License v3.0**.

Copyright (C) 2026 Diego Alejandro Botina.

Ver el archivo [`LICENSE`](./LICENSE) para el texto completo.
