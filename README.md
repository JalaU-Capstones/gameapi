# GameAPI

REST API para gestión de usuarios y partidas de Tic-Tac-Toe.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![codecov](https://codecov.io/gh/JalaU-Capstones/gameapi/branch/main/graph/badge.svg)](https://codecov.io/gh/JalaU-Capstones/gameapi)
[![Render](https://img.shields.io/badge/Render-production-46E3B7?logo=render&logoColor=white)](https://gameapi-9vos.onrender.com/health)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Tests](https://img.shields.io/badge/tests-286%20passed-success.svg)](#pruebas)
[![Coverage](https://img.shields.io/badge/coverage-94.75%25-brightgreen.svg)](#cobertura)

**Stack:** Python 3.11+ · FastAPI · PostgreSQL 16 · SQLAlchemy 2.0 async · Pydantic v2 · JWT · WebSocket · uv · Docker

---

## Tabla de contenidos

- [Características](#características)
- [Requisitos](#requisitos)
- [Clonación](#clonación)
- [Instalación](#instalación)
- [Guía del Makefile](#guía-del-makefile)
- [Configuración](#configuración)
- [Ejecución](#ejecución)
- [Endpoints](#endpoints)
- [Colecciones de cliente](#colecciones-de-cliente)
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
- Juego en tiempo real sobre WebSocket: invitaciones, turnos, detección de victoria/empate/abandono y broadcast del estado a ambos jugadores.
- Registro persistente de eventos de aplicación con escritura por lotes, retención configurable y consulta protegida.
- Dockerizado con healthchecks y multi-stage build.

---

## Requisitos

Antes de instalar, asegúrate de tener:

| Herramienta              | Versión mínima      | Instalación                                        |
|--------------------------|---------------------|----------------------------------------------------|
| **Python**               | 3.11+               | <https://www.python.org/downloads/>                |
| **uv**                   | 0.4+                | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Git**                  | 2.30+               | <https://git-scm.com/downloads>                    |
| **PostgreSQL**           | 16                  | <https://www.postgresql.org/download/>             |
| **Docker** + **Compose** | 24+ / v2 (opcional) | <https://docs.docker.com/get-docker/>              |

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

## Guía del Makefile

El proyecto incluye un `Makefile` que envuelve los comandos más comunes.
Ejecuta `make help` para ver la lista completa.

### Desarrollo

| Comando             | Descripción                                              |
|---------------------|----------------------------------------------------------|
| `make install`      | Instala dependencias con `uv sync`                       |
| `make dev`          | Arranca el servidor con recarga en caliente              |
| `make run`          | Arranca el servidor en modo producción                   |

### Calidad de código

| Comando                   | Descripción                                  |
|---------------------------|----------------------------------------------|
| `make lint`               | Ejecuta `ruff check .`                       |
| `make format`             | Ejecuta `ruff format .`                      |
| `make typecheck`          | Ejecuta `mypy src` con `strict`              |
| `make pre-commit`         | Ejecuta todos los hooks de pre-commit        |
| `make pre-commit-install` | Instala los hooks de pre-commit una sola vez |

### Pruebas

| Comando             | Descripción                                              |
|---------------------|----------------------------------------------------------|
| `make test`         | Ejecuta pytest                                           |
| `make test-cov`     | Ejecuta pytest con cobertura y umbral del 93%            |
| `make test-clean`   | Elimina contenedores residuales de testcontainers        |

### Migraciones

| Comando               | Descripción                                 |
|-----------------------|---------------------------------------------|
| `make migrate`        | Aplica migraciones Alembic (`upgrade head`) |
| `make migrate-create` | Crea una migración autogenerada             |

### Contratos de API

| Comando                  | Descripción                                           |
|--------------------------|-------------------------------------------------------|
| `make openapi-export`    | Regenera `.docs/contracts/openapi/openapi.json`       |
| `make openapi-check`     | Verifica que el contrato commiteado esté sincronizado |
| `make asyncapi-validate` | Valida el contrato AsyncAPI contra el spec            |
| `make contracts-check`   | Ejecuta ambas validaciones                            |

### Docker

| Comando             | Descripción                                              |
|---------------------|----------------------------------------------------------|
| `make docker-up`    | Levanta PostgreSQL y la API con `docker compose up -d`   |
| `make docker-down`  | Detiene los contenedores (conserva volúmenes)            |
| `make docker-logs`  | Muestra logs en vivo del contenedor `api`                |
| `make docker-reset` | Detiene contenedores y borra volúmenes (`-v`)            |

### Limpieza

| Comando             | Descripción                                              |
|---------------------|----------------------------------------------------------|
| `make clean`        | Borra cachés (`__pycache__`, `.pytest_cache`, etc.)      |

### Flujo típico de un desarrollador

```bash
make install              # Primera vez: instalar dependencias
cp .env.example .env      # Primera vez: crear el archivo de entorno
make dev                  # Arrancar el servidor en local

# Antes de commitear
make format
make lint
make typecheck
make test
make test-cov

# Para probar todo el stack con Docker
make docker-up
make migrate              # Si no se aplicó automáticamente
curl http://localhost:8080/health
make docker-down
```

---

## Configuración

Todas las variables se leen desde `.env` (ver `.env.example`):

| Variable                           | Descripción                                         | Default                                                       |
|------------------------------------|-----------------------------------------------------|---------------------------------------------------------------|
| `POSTGRES_URI` | URI de PostgreSQL. Acepta `postgres://`, `postgresql://` o `postgresql+asyncpg://` y normaliza al driver async automáticamente. | `postgresql+asyncpg://gameapi:gameapi@localhost:5432/gameapi` |
| `POSTGRES_USER`                    | Usuario de PostgreSQL (para Docker Compose)         | `gameapi`                                                     |
| `POSTGRES_PASSWORD`                | Contraseña de PostgreSQL (para Docker Compose)      | `gameapi`                                                     |
| `POSTGRES_DB`                      | Nombre de la base de datos PostgreSQL               | `gameapi`                                                     |
| `POSTGRES_PORT`                    | Puerto host de PostgreSQL (para Docker Compose)     | `5432`                                                        |
| `JWT_SECRET_KEY`                   | Clave secreta para firmar JWT (mín. 32 caracteres)  | *(requerido)*                                                 |
| `JWT_ALGORITHM`                    | Algoritmo de firma                                  | `HS256`                                                       |
| `JWT_ISSUER`                       | Emisor del token                                    | `GameAPI`                                                     |
| `JWT_AUDIENCE`                     | Audiencia del token                                 | `GameAPI`                                                     |
| `JWT_EXPIRE_MINUTES`               | Expiración del token en minutos                     | `60`                                                          |
| `APP_ENV`                          | Entorno (`development` / `staging` / `production`)  | `development`                                                 |
| `APP_HOST`                         | Host de escucha                                     | `0.0.0.0`                                                     |
| `APP_PORT`                         | Puerto de escucha                                   | `8080`                                                        |
| `CORS_ORIGINS`                     | Orígenes permitidos (coma-separados o `*`)          | `*`                                                           |
| `LOG_BUFFER_SIZE`                  | Cantidad de eventos por lote                        | `100`                                                         |
| `LOG_FLUSH_INTERVAL_SECONDS`       | Intervalo máximo entre escrituras                   | `5.0`                                                         |
| `LOG_RETENTION_DAYS`               | Días que se conservan los logs                      | `30`                                                          |
| `LOG_QUEUE_MAXSIZE`                | Capacidad de la cola de logs                        | `1000`                                                        |
| `LOG_ADMIN_EMAILS`                 | Correos con acceso al endpoint global de logs (CSV) | _(vacío)_                                                     |
| `AUTH_ACCESS_COOKIE_NAME`          | Nombre de la cookie del access token                | `gameapi_at`                                                  |
| `AUTH_REFRESH_COOKIE_NAME`         | Nombre de la cookie del refresh token               | `gameapi_rt`                                                  |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | Expiración del access token                         | `15`                                                          |
| `AUTH_REFRESH_TOKEN_EXPIRE_DAYS`   | Expiración del refresh token                        | `7`                                                           |
| `AUTH_COOKIE_SECURE`               | Envía la cookie solo sobre HTTPS                    | `false`                                                       |
| `AUTH_COOKIE_SAMESITE`             | Política SameSite                                   | `lax`                                                         |
| `AUTH_COOKIE_DOMAIN`               | Dominio opcional para cookies                       | *(vacío)*                                                     |
| `AUTH_REFRESH_COOKIE_PATH`         | Path del refresh cookie                             | `/api/v2/auth`                                                |
| `AUTH_ACCESS_COOKIE_PATH`          | Path del access cookie                              | `/`                                                           |

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

| Recurso      | URL                                  |
|--------------|--------------------------------------|
| API          | <http://localhost:8080>              |
| Swagger UI   | <http://localhost:8080/docs>         |
| ReDoc        | <http://localhost:8080/redoc>        |
| OpenAPI JSON | <http://localhost:8080/openapi.json> |
| Health check | <http://localhost:8080/health>       |

---

## Endpoints

### Versionado de la API

El proyecto mantiene dos contratos activos:

- `/api/v1`: versión congelada, compatible con el contrato legado original.
- `/api/v2`: versión activa para nuevas integraciones y WebSockets.

> La versión v1 queda fija para compatibilidad. La v2 puede evolucionar sin romper la v1.

## Autenticación

El backend soporta dos mecanismos de autenticación simultáneamente:

### 1. Cookie HttpOnly (recomendado para el frontend)

Los endpoints `/api/v2/auth/*` establecen cookies HttpOnly tras un login exitoso. El frontend no necesita manipular el token: el navegador lo envía automáticamente en cada request posterior.

- `gameapi_at` — access token (15 minutos).
- `gameapi_rt` — refresh token (7 días), enviado solo a `/api/v2/auth`.

### 2. Bearer header (compatible con CLI, Postman, Insomnia)

El login tradicional sigue devolviendo el access token en el body. Se puede usar como `Authorization: Bearer <token>`. Este es el modo por defecto para herramientas de testing y scripts.

### Endpoints

| Método | Ruta                   | Auth | Descripción                                 |
|--------|------------------------|------|---------------------------------------------|
| `POST` | `/api/v2/auth/login`   | ❌   | Login: setea cookies + devuelve token.      |
| `POST` | `/api/v2/auth/refresh` | 🔄   | Rota el refresh token y emite nuevo access. |
| `POST` | `/api/v2/auth/logout`  | 🔄   | Revoca refresh token y limpia cookies.      |
| `GET`  | `/api/v2/auth/me`      | ✅   | Usuario actual (desde cookie o header).     |

### Variables de entorno relacionadas

| Variable                           | Default        | Descripción                                |
|------------------------------------|----------------|--------------------------------------------|
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | 15             | Expiración del access token                |
| `AUTH_REFRESH_TOKEN_EXPIRE_DAYS`   | 7              | Expiración del refresh token               |
| `AUTH_COOKIE_SECURE`               | `false`        | `true` en producción (HTTPS)               |
| `AUTH_COOKIE_SAMESITE`             | `lax`          | `none` requiere `AUTH_COOKIE_SECURE=true`  |
| `AUTH_COOKIE_DOMAIN`               | _(vacío)_      | Dominio de la cookie (ej. `.onrender.com`) |
| `AUTH_REFRESH_COOKIE_PATH`         | `/api/v2/auth` | Path de la cookie de refresh               |
| `AUTH_ACCESS_COOKIE_PATH`          | `/`            | Path de la cookie de access                |

### Usuarios v1 y v2

| Método   | Ruta                  | Auth | Descripción                     |
|----------|-----------------------|------|---------------------------------|
| `POST`   | `/api/v1/users`       | ❌   | Registrar usuario               |
| `GET`    | `/api/v1/users`       | ❌   | Listar usuarios                 |
| `GET`    | `/api/v1/users/{id}`  | ❌   | Obtener un usuario              |
| `PUT`    | `/api/v1/users/{id}`  | ✅   | Actualizar **tu propia** cuenta |
| `DELETE` | `/api/v1/users/{id}`  | ✅   | Eliminar **tu propia** cuenta   |
| `POST`   | `/api/v1/users/login` | ❌   | Login (devuelve JWT)            |
| `POST`   | `/api/v2/users`       | ❌   | Mismo contrato v2               |
| `GET`    | `/api/v2/users`       | ❌   | Mismo contrato v2               |
| `GET`    | `/api/v2/users/{id}`  | ❌   | Mismo contrato v2               |
| `PUT`    | `/api/v2/users/{id}`  | ✅   | Mismo contrato v2               |
| `DELETE` | `/api/v2/users/{id}`  | ✅   | Mismo contrato v2               |
| `POST`   | `/api/v2/users/login` | ❌   | Mismo contrato v2               |

### Gameplays v1 y v2

| Método   | Ruta                             | Auth | Descripción                      |
|----------|----------------------------------|------|----------------------------------|
| `GET`    | `/api/v1/gameplays`              | ❌   | Listar todas las partidas        |
| `GET`    | `/api/v1/gameplays/my-gameplays` | ✅   | Partidas del usuario autenticado |
| `GET`    | `/api/v1/gameplays/player/{id}`  | ❌   | Partidas de un jugador           |
| `GET`    | `/api/v1/gameplays/{id}`         | ❌   | Obtener una partida              |
| `POST`   | `/api/v1/gameplays`              | ✅   | Crear partida (host = tú)        |
| `PUT`    | `/api/v1/gameplays/{id}`         | ✅   | Actualizar (solo participantes)  |
| `DELETE` | `/api/v1/gameplays/{id}`         | ✅   | Eliminar (solo host)             |
| `GET`    | `/api/v2/gameplays`              | ❌   | Mismo contrato v2                |
| `GET`    | `/api/v2/gameplays/my-gameplays` | ✅   | Mismo contrato v2                |
| `GET`    | `/api/v2/gameplays/player/{id}`  | ❌   | Mismo contrato v2                |
| `GET`    | `/api/v2/gameplays/{id}`         | ❌   | Mismo contrato v2                |
| `POST`   | `/api/v2/gameplays`              | ✅   | Mismo contrato v2                |
| `PUT`    | `/api/v2/gameplays/{id}`         | ✅   | Mismo contrato v2                |
| `DELETE` | `/api/v2/gameplays/{id}`         | ✅   | Mismo contrato v2                |

### Logs v2

Los logs se pueden consultar a través de dos endpoints bajo `/api/v2/logs`, ambos protegidos con JWT:

| Método | Ruta              | Auth | Descripción                                             |
|--------|-------------------|------|---------------------------------------------------------|
| `GET`  | `/api/v2/logs/me` | ✅   | Logs del usuario autenticado. Siempre disponible.       |
| `GET`  | `/api/v2/logs`    | ✅   | Logs de todos los usuarios. Requiere ser administrador. |

**Autorización de administrador**

El proyecto no tiene un sistema de roles formal. Para el endpoint global se usa una lista de correos configurada por la variable de entorno `LOG_ADMIN_EMAILS` (separada por comas). Si el correo del usuario autenticado no está en la lista, el endpoint devuelve **403**. La lista está vacía por defecto, por lo que el acceso global queda deshabilitado hasta configurar al menos un administrador.

Cuando se implemente un sistema de roles formal, esta validación se reemplaza por una verificación de rol sin cambiar la API pública.

**Parámetros de consulta:**

| Parámetro     | Tipo         | Descripción                                   |
|---------------|--------------|-----------------------------------------------|
| `level`       | string       | Nivel, por ejemplo `INFO`, `WARN` o `ERROR`   |
| `event_type`  | string       | Tipo de evento, por ejemplo `user_registered` |
| `gameplay_id` | UUID         | Filtrar por partida                           |
| `from`        | ISO datetime | Timestamp mínimo                              |
| `to`          | ISO datetime | Timestamp máximo                              |
| `limit`       | int (1–200)  | Predeterminado 50                             |
| `offset`      | int (≥0)     | Predeterminado 0                              |

En `/api/v2/logs/me` no existe el parámetro `player_id`: siempre filtra por el usuario autenticado. FastAPI ignora parámetros desconocidos, por lo que enviar `player_id` no cambia el filtro. En `/api/v2/logs` (administrador) sí está disponible para buscar logs de un usuario específico. Los resultados se ordenan del más reciente al más antiguo; los eventos se escriben por lotes y se eliminan según `LOG_RETENTION_DAYS`.

**Seguridad entre hilos del handler**

`asyncio.Queue` no es segura entre hilos. Como el handler está conectado al root logger global, los mensajes pueden llegar desde hilos distintos al event loop, como workers de anyio, pools de threads o librerías de terceros. El handler los envía a la cola mediante `loop.call_soon_threadsafe`, lo que mantiene la integridad de la cola en Python 3.11+ sin bloquear el hilo emisor.

### WebSockets v2

Los endpoints WebSocket operan bajo `/api/v2/ws` y requieren autenticación JWT mediante el primer mensaje JSON.

| Ruta                   | Descripción                                                                       |
|------------------------|-----------------------------------------------------------------------------------|
| `/api/v2/ws/gameplays` | Canal de eventos de partidas. Requiere el evento `auth` con `{ "token": "..." }`. |
| `/api/v2/ws/presence`  | Canal de presencia en línea. Requiere el evento `auth` con `{ "token": "..." }`.  |

**Eventos soportados actualmente (B3):**

**Cliente → Servidor:**
- `auth` — primer mensaje obligatorio con el JWT.
- `ping` — keepalive.
- `create_game` — crear partida e invitar. Payload: `{"guest_id": "<uuid>"}`.
- `accept_invitation` — aceptar invitación. Payload: `{"game_id": "<uuid>"}`.
- `reject_invitation` — rechazar invitación. Payload: `{"game_id": "<uuid>"}`.
- `play_move` — jugar. Payload: `{"game_id": "<uuid>", "row": 0-2, "col": 0-2}`.
- `leave_game` — abandonar partida activa. Payload: `{"game_id": "<uuid>"}`.
- `subscribe_game` — unirse al canal de una partida.
- `unsubscribe_game` — salir del canal.

**Servidor → Cliente:**
- `auth_ok` / `auth_error` — resultado de autenticación.
- `pong` — respuesta a `ping`.
- `game_created` — partida creada (al host).
- `invitation_received` — invitación entrante (al guest).
- `invitation_accepted` — el guest aceptó; partida comienza (a ambos).
- `invitation_rejected` — el guest rechazó (al host).
- `board_updated` — jugada realizada. Incluye `board`, `turn` y `last_move`.
- `game_ended` — partida terminada. Incluye `game_id`, `board`, `winner`, `reason`, y `winner_line` (`null` para empate/abandono, una lista de coordenadas para victoria).
- `subscribed` / `unsubscribed` — confirmación de suscripción al canal.
- `error` — error de validación. Incluye `code` y `message`.

**Códigos de error soportados:**

`NOT_YOUR_TURN`, `INVALID_MOVE`, `GAME_NOT_FOUND`, `GAME_NOT_ACTIVE`,
`NOT_A_PARTICIPANT`, `INVITATION_NOT_PENDING`, `CANNOT_INVITE_SELF`,
`OPPONENT_OFFLINE`, `INVALID_PAYLOAD`, `INVALID_EVENT`, `NOT_IMPLEMENTED`.

#### Protocolo de autenticación WS

```json
{"event": "auth", "payload": {"token": "<jwt>"}}
```

Respuesta exitosa:

```json
{"event": "auth_ok", "payload": {"user_id": "<uuid>"}}
```

Errores:

```json
{"event": "auth_error", "payload": {"reason": "invalid_token"}}
```

Eventos soportados:

- `ping` → responde `pong`
- `list_online_users` (presencia) → devuelve usuarios conectados
- Cualquier otro evento sin implementar devuelve `error`

### Ejemplos con `curl`

Todos los ejemplos usan `localhost:8080`. La API está versionada; el prefijo
`/api/v1` corresponde al contrato congelado y `/api/v2` a la versión activa.

#### Registro de usuario (v2, recomendado)

Crea el usuario y lo autentica en una sola llamada (auto-login con cookies
HttpOnly).

```bash
curl -i -c cookies.txt -X POST http://localhost:8080/api/v2/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Sandra Dee","email":"sandra@mail.com","password":"password123"}'
```

Respuesta `201 Created` con `Set-Cookie: gameapi_at` y
`Set-Cookie: gameapi_rt`. También incluye un `access_token` en el body para
clientes basados en header.

#### Login (v2)

```bash
curl -i -c cookies.txt -X POST http://localhost:8080/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sandra@mail.com","password":"password123"}'
```

#### Login (v1, contrato legacy)

El login de v1 sigue disponible y devuelve el token en el body. Es útil para
herramientas que usan `Authorization: Bearer`.

Bash:

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sandra@mail.com","password":"password123"}' | jq -r .token)
```

Fish shell:

```fish
set TOKEN (curl -s -X POST http://localhost:8080/api/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sandra@mail.com","password":"password123"}' | jq -r .token)
```

#### Consultar el usuario autenticado

Con cookies (frontend):

```bash
curl -b cookies.txt http://localhost:8080/api/v2/auth/me | jq
```

Con header `Authorization`:

```bash
curl -H "Authorization: ******" http://localhost:8080/api/v2/auth/me | jq
```

#### Listar usuarios (v1, requiere autenticación)

```bash
curl -H "Authorization: ******" http://localhost:8080/api/v1/users | jq
```

#### Crear una partida vía REST (v1, requiere autenticación)

```bash
curl -X POST http://localhost:8080/api/v1/gameplays \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "currentPositions": "{\"board\": [[0,0,0],[0,0,0],[0,0,0]], \"lastMove\": null}",
    "hostPlayer": "USER_ID",
    "playerTurn": "USER_ID"
  }'
```

> **Nota:** la creación de partidas en v2 se realiza por WebSocket
> (`create_game`). El endpoint REST de v1 se mantiene por compatibilidad con
> el contrato congelado.

#### Consultar mis partidas (v2, requiere autenticación)

```bash
curl -b cookies.txt http://localhost:8080/api/v2/gameplays/my-gameplays | jq
```

#### Consultar mis logs (v2, requiere autenticación)

```bash
curl -b cookies.txt "http://localhost:8080/api/v2/logs/me?limit=10" | jq
```

#### Health check

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

#### Colecciones de cliente

Ver [`.docs/collections/`](./.docs/collections/README.md) para instrucciones
detalladas sobre Postman e Insomnia.

---

## Colecciones de cliente

El repositorio incluye dos colecciones para probar la API manualmente desde un cliente HTTP/WebSocket:

| Herramienta  | Cubre            | Archivo                                                                                          |
|--------------|------------------|--------------------------------------------------------------------------------------------------|
| **Postman**  | Solo REST        | [`GameAPI.postman_collection.json`](./.docs/collections/postman/GameAPI.postman_collection.json) |
| **Insomnia** | REST + WebSocket | [`GameAPI.insomnia.yaml`](./.docs/collections/insomnia/GameAPI.insomnia.yaml)                    |

> **Nota**: la colección de Postman **no incluye los endpoints WebSocket**. Postman no maneja bien colecciones mixtas REST + WS (convierte los requests WS a HTTP y falla con `Invalid protocol: ws:`), por lo que Insomnia es la herramienta recomendada para el flujo completo. Ver [la explicación completa](./.docs/collections/README.md#why-two-collections).

Ambas colecciones incluyen:

- **Login automático** que guarda el token en una variable (`{{token}}` en Postman, `{{ _.token }}` en Insomnia).
- **Documentación por request** visible en el panel **Documentation** (Postman) o **Docs** (Insomnia).
- **Scripts de respuesta** que capturan `userId` y `gameplayId` tras las operaciones de creación.

Para el detalle de por qué hay dos colecciones, el flujo recomendado y la solución de problemas (auth timeout, curl sin soporte `--ws`, etc.), consulta [`.docs/collections/README.md`](./.docs/collections/README.md).

---

## Contratos de API

Los contratos formales de la API — OpenAPI para REST y AsyncAPI para WebSocket — viven en el repositorio bajo `.docs/contracts/`. Son la fuente de verdad para todos los clientes y se validan automáticamente en CI.

- **Contrato REST (v1 + v2):** `.docs/contracts/openapi/openapi.json` — generado desde el código FastAPI.
- **Contrato WebSocket (v2):** `.docs/contracts/asyncapi/asyncapi.json` — mantenido manualmente.
- **Política de versionado y mantenimiento:** ver `.docs/contracts/README.md`.

---

## Pruebas

```bash
make test
```

Salida esperada:

```
286 passed in ~3s
Required test coverage of 93.0% reached. Total coverage: 94.75%
```

Los tests usan **PostgreSQL** de dos formas según el entorno:

- **Local:** levantan un contenedor efímero con `testcontainers[postgresql]`.
  Requieren Docker corriendo. La primera ejecución descarga la imagen
  `postgres:16-alpine` (~100 MB).
- **CI:** usan un servicio PostgreSQL nativo del runner, configurado vía la
  variable de entorno `TEST_POSTGRES_URI`. Esto evita la sobrecarga de
  Docker-in-Docker y hace los pipelines más rápidos y fiables.

Para correr los tests con cobertura:

```bash
make test-cov
```

### Bus de eventos

El proyecto usa un **EventBus in-process** (`services/event_bus.py`) para desacoplar los handlers de WebSocket de la lógica de dominio. Cada partida tiene su propio canal, y los clientes se suscriben al canal al entrar a una partida.

- **Arquitectura:** un `asyncio.Queue` + un worker task por canal.
- **API:** `subscribe(channel, subscriber_id, callback)`, `unsubscribe(channel, subscriber_id)`, `publish(channel, event)`.
- **Limpieza automática:** al quedarse sin suscriptores, el canal se destruye y su worker se cancela.
- **Sin estado persistente:** todo vive en memoria del proceso. Un reinicio limpia las suscripciones.
- **Upgrade path:** si se necesita escalar horizontalmente, se puede reemplazar por Redis Pub/Sub sin cambiar la API del bus.

### Reglas del juego (Tic-Tac-Toe)

El motor del juego vive en `services/game_engine.py` (reglas puras, sin I/O) y
se orquesta desde `services/game_engine_service.py` (persistencia + broadcast).

- **Tablero:** 3×3 representado como `[[0,0,0],[0,0,0],[0,0,0]]`. Celdas: `0`
  vacía, `1` jugada del host, `2` jugada del guest.
- **Turnos:** el host siempre empieza. Cada jugada válida cambia el turno al
  oponente.
- **Victoria:** el primero en completar 3 en línea (fila, columna o diagonal)
  gana. Se detecta con `check_winner()`.
- **Empate:** si el tablero se llena sin ganador, se marca `reason: "draw"`.
- **Abandono:** si un jugador se desconecta durante una partida activa, el
  oponente gana con `reason: "abandon"`.
- **Rechazo:** si el guest rechaza la invitación, se marca como terminada con
  `reason: "rejected"` y el host es notificado.

**Estados del juego** (basados en `match_result` y `player_turn` en la BD):

| `match_result`                       | `player_turn` | Estado               |
|--------------------------------------|---------------|----------------------|
| `{"reason": "pending"}`              | _(asignado)_  | Invitación pendiente |
| `null`                               | no nulo       | En curso             |
| `{"winner": "...", "reason": "..."}` | cualquiera    | Finalizado           |

### Cobertura

**Umbral mínimo:** 93% (configurado en `pyproject.toml` → `[tool.coverage.report] fail_under`).

**Cobertura actual:** 94.75% (reporte medido con `coverage report --precision=2`).

| Archivo                                  | Tests | Qué cubre                                                                   |
|------------------------------------------|-------|-----------------------------------------------------------------------------|
| `tests/test_security.py`                 | 4     | Hashing bcrypt, JWT create/decode, token manipulado.                        |
| `tests/test_health.py`                   | 2     | Endpoint `/health` y ciclo de vida de la aplicación.                        |
| `tests/test_users.py`                    | 21    | CRUD de usuarios, validación, permisos e invariantes de identidad.          |
| `tests/test_gameplays.py`                | 23    | CRUD de gameplays + validación JSON + permisos + UUID válido inexistente.   |
| `tests/test_edge_cases.py`               | 16    | UUIDs inválidos, errores de auth, validaciones.                             |
| `tests/test_services_unit.py`            | 16    | Servicios, configuración, entrypoint y repositorio de logs.                 |
| `tests/test_game_engine_service_unit.py` | 18    | Excepciones, turnos, victoria, empate, abandono y rechazo.                 |
| `tests/test_api_deps.py`                 | 2     | Sesión de base de datos y autenticación de cuentas eliminadas.              |
| `tests/test_ws_manager.py`               | 2     | Envío a usuarios desconectados y limpieza de sockets fallidos.              |
| `tests/test_event_bus.py`                | 9     | Pub/sub del bus, multi-suscriptor, shutdown.                                |
| `tests/test_game_engine.py`              | 25    | Reglas puras de Tic-Tac-Toe, líneas ganadoras y casos de empate.           |
| `tests/test_ws_gameplays.py`             | 11    | Auth WS, ping/pong, subscribe/unsubscribe, cleanup.                         |
| `tests/test_ws_game_flow.py`             | 12    | Flujo completo de partida, rechazo, abandono, empate y errores WS.         |
| `tests/test_ws_presence.py`             | 10    | Presencia en línea y eventos de conexión/desconexión.                      |              | 10    | Presencia online/offline, listado, mensajes inválidos y autenticación.      || `tests/test_ws_game_flow.py`             | 11    | Flujo completo de partida (happy path, rechazo, abandono, empate, errores). |

**Reporte HTML** (local, tras `make test-cov`):

```bash
open htmlcov/index.html
```

**Reporte XML** (generado con Coverage.py para CI): `coverage.xml` → subido a Codecov en cada push a `main`.

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

- `quality`: ruff + mypy (Python 3.12).
- `test`: matriz de compatibilidad **Python 3.11 / 3.12 / 3.13 / 3.14**, cada
  versión ejecuta los tests con cobertura (`coverage run` + `--fail-under=93`)
  contra un servicio PostgreSQL 16. El reporte se sube a Codecov una sola vez
  desde Python 3.14.
- `docker`: build de la imagen + smoke test con PostgreSQL en red dedicada.

**GitLab CI** (`.gitlab-ci.yml`) — mismo esquema: `test:python` corre la matriz
3.11–3.14 con cobertura y umbral del 93% aplicado en cada versión.

**Dependabot** (`.github/dependabot.yml`) — PR semanal para `uv.lock` y
GitHub Actions.

**Nota sobre la medición de cobertura**
El proyecto declara `concurrency = ["thread", "greenlet"]` en la configuración
de Coverage.py. SQLAlchemy async usa greenlets internamente para gestionar el
contexto de las coroutines, y Coverage.py requiere esta declaración explícita
para rastrear los frames correctamente en Python 3.11–3.14. Sin esta
configuración, la cobertura se reportaba erróneamente en versiones anteriores
a 3.14.

---

## Docker

```bash
make docker-up     # construir y levantar (postgres + api)
make docker-logs   # ver logs en vivo
make docker-down   # detener (conserva volúmenes)
make docker-reset  # detener y borrar datos
```

Detalles:

- Imagen de la API: multi-stage build (`ghcr.io/astral-sh/uv` + `python:3.13-slim-bookworm`).
- Usuario no-root en el contenedor.
- Healthchecks reales para PostgreSQL y la API.
- La API espera a que PostgreSQL esté `healthy` antes de arrancar.

### Redes y permisos locales

Compose conecta la API a `frontend` (bridge, con el puerto 8080 publicado en el host) y a
`backend`. Esta última red es `internal: true`: permite la comunicación entre la API y
PostgreSQL sin exponer el servicio mediante un puerto publicado ni proporcionar salida a
redes externas. PostgreSQL no publica el puerto 5432. Para administrarlo, ejecuta:

```bash
docker compose exec postgres psql -U gameapi -d gameapi
```

En el host, `localhost:5432` no está publicado. En Linux, el host Docker todavía puede
tener conectividad directa a la IP interna del contenedor; `internal: true` no sustituye
una regla de firewall del host si también se necesita bloquear ese acceso directo.

El sistema de archivos raíz de la API es de solo lectura. Los archivos temporales deben
escribirse en `/tmp` o `/run`, que son montajes temporales en memoria y no persisten.
Este endurecimiento corresponde únicamente al entorno local de Compose; Render gestiona
su propio runtime y no utiliza esta configuración.

### Flujo completo con Docker

```bash
# 1. Levantar la pila (PostgreSQL + API)
make docker-up

# 2. Esperar a que los contenedores estén healthy
docker compose ps

# 3. Aplicar migraciones (si el container no las aplica automáticamente)
make migrate

# 4. Verificar que todo funciona
curl http://localhost:8080/health
# → {"status":"ok"}

# 5. Detener
make docker-down
```

> Si el contenedor de la API no puede conectarse a PostgreSQL, revisa el
> log con `docker compose logs api`. La causa más común es un valor
> incorrecto de `POSTGRES_URI` en `.env` — dentro de la red de Docker debe
> apuntar al servicio `postgres`, no a `localhost`.

---

## Arquitectura

```
gameapi/
├── src/gameapi/
│   ├── core/            # Config, seguridad (JWT + bcrypt)
│   ├── db/              # SQLAlchemy ORM + session management
│   ├── repositories/    # Data access layer (queries SQLAlchemy)
│   ├── schemas/         # Contratos de API (camelCase, validación)
│   │   ├── ...
│   │   └── ws_events.py         # Payloads tipados de eventos WebSocket
│   ├── services/        # Lógica de negocio async, errores de dominio
│   │   ├── ...
│   │   ├── event_bus.py         # Pub/sub in-process por canal (gameplay)
│   │   ├── game_engine.py       # Reglas puras de Tic-Tac-Toe (sin I/O)
│   │   ├── game_engine_service.py  # Orquestación: reglas + persistencia + bus
│   │   └── ...
│   ├── api/             # Routers FastAPI + dependencias (auth, DI)
│   │   ├── v1/          # Congelado (compatibilidad legacy C#)
│   │   └── v2/          # Activo: REST + WebSocket
│   │       └── ws/      # Endpoints WebSocket (auth, manager, gameplays, presence)
│   └── main.py          # App FastAPI, lifespan, CORS, exception handlers
├── migrations/          # Migraciones Alembic
├── tests/               # pytest + httpx + PostgreSQL (local/CI dual-mode)
├── .docs/collections/   # Colecciones Postman e Insomnia
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

| Capa                                                          | Convención   | Motivo                                                     |
|---------------------------------------------------------------|--------------|------------------------------------------------------------|
| Python interno (`db/`, `repositories/`, `services/`, `core/`) | `snake_case` | PEP 8 — estilo idiomático de Python                        |
| API pública (JSON entrada/salida)                             | `camelCase`  | Compatibilidad con clientes existentes (frontend, Postman) |

La conversión es **automática** vía `pydantic.alias_generators.to_camel` en `schemas/base.py::ApiModel`.

### Tabla de mapeo

**Usuarios:**

| Python          | JSON           |
|-----------------|----------------|
| `id`            | `id`           |
| `name`          | `name`         |
| `email`         | `email`        |
| `register_date` | `registerDate` |

**Partidas:**

| Python              | JSON               |
|---------------------|--------------------|
| `id`                | `id`               |
| `current_positions` | `currentPositions` |
| `host_player`       | `hostPlayer`       |
| `guest_player`      | `guestPlayer`      |
| `player_turn`       | `playerTurn`       |
| `match_result`      | `matchResult`      |
| `created_date`      | `createdDate`      |
| `updated_date`      | `updatedDate`      |

### Reglas para contribuir

1. **Modelos de dominio y servicios** → siempre `snake_case`.
2. **Schemas de API** → declarar en `snake_case`; el alias `camelCase` se genera solo.
3. **Nunca** exponer los modelos ORM directamente en la API; siempre traducir a schemas Pydantic.
4. Al agregar un endpoint, exponer el **schema** (nunca el `*Document`).
5. Antes de commitear: `make format && make lint && make typecheck && make test && make test-cov`.

---

## Seguridad

- Contraseñas hasheadas con **bcrypt** (con pre-hash SHA-256 para soportar passwords largas).
- Tokens JWT firmados con **HS256**; validación de `iss`, `aud`, `exp`, `iat`, `jti`.
- Validación de email único (constraint `UNIQUE` en PostgreSQL).
- Endpoints protegidos con `HTTPBearer`.
- Ownership check: un usuario solo puede modificar/eliminar sus propios recursos.
- CORS configurable por entorno.
- `JWT_SECRET_KEY` mínimo 32 caracteres (validado en el arranque).
- Límite de tasa por cliente y ruta con SlowAPI para mitigar fuerza bruta e intentos de abuso; ver [Rate limiting](./.docs/rate-limiting/README.md).

### Endurecimiento en producción

Cuando `APP_ENV=production`, el backend valida en el arranque que:

- `JWT_SECRET_KEY` no sea el valor por defecto.
- `AUTH_COOKIE_SECURE` sea `true` (cookies solo sobre HTTPS).
- `CORS_ORIGINS` no sea `*` (browsers rechazan cookies con wildcard).

Si alguna condición falla, la aplicación no arranca y el error aparece en los logs del contenedor. Esto previene despliegues accidentales con configuración de desarrollo.

---

## Despliegue

El backend se despliega en **Render** con PostgreSQL gestionado. El deploy es automático: cada push a `main` con CI en verde dispara un deploy en Render vía GitHub Actions.

- **Guía completa:** [`.docs/deployment/README.md`](./.docs/deployment/README.md)
- **Blueprint declarativo:** [`render.yaml`](./render.yaml)
- **Workflow de deploy:** [`.github/workflows/deploy.yml`](./.github/workflows/deploy.yml)

**Resumen rápido:**

1. La base de datos PostgreSQL se crea primero en Render.
2. El Web Service consume la URI interna vía `POSTGRES_URI`.
3. Los secretos viven en Render (dashboard), no en el repositorio.
4. GitHub Actions dispara el deploy con un POST al deploy hook.

## Licencia

Este proyecto está bajo la **GNU General Public License v3.0**.

Copyright (C) 2026 Diego Alejandro Botina.

Ver el archivo [`LICENSE`](./LICENSE) para el texto completo.
