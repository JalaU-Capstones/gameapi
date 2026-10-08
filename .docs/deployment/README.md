# Guía de despliegue en Render

Esta guía describe cómo desplegar el backend `GameAPI` en Render desde cero.
Está pensada para que cualquier persona pueda levantar su propia instancia y
para que el equipo tenga una referencia clara del flujo de despliegue.

## Instancia de referencia

La instancia de producción del equipo está disponible en
<https://gameapi-9vos.onrender.com>.

| Recurso | URL |
|---|---|
| API | <https://gameapi-9vos.onrender.com> |
| Swagger UI | <https://gameapi-9vos.onrender.com/docs> |
| ReDoc | <https://gameapi-9vos.onrender.com/redoc> |
| OpenAPI JSON | <https://gameapi-9vos.onrender.com/openapi.json> |
| Health check | <https://gameapi-9vos.onrender.com/health> |
| WebSocket gameplays | `wss://gameapi-9vos.onrender.com/api/v2/ws/gameplays` |
| WebSocket presence | `wss://gameapi-9vos.onrender.com/api/v2/ws/presence` |

La instancia usa el plan gratuito de Render: se suspende tras 15 minutos de
inactividad y la primera petición después de un arranque en frío puede tardar
entre 30 y 60 segundos.

## Arquitectura de despliegue

```mermaid
flowchart LR
    Dev["Developer"] -->|"push a main"| GH["GitHub"]
    GH -->|"CI verde"| Actions["GitHub Actions<br/>deploy.yml"]
    Actions -->|"POST deploy hook"| Render
    subgraph Render["Render Cloud"]
        DB[("PostgreSQL<br/>gameapi-db")]
        API["Web Service<br/>gameapi"]
        API --> DB
    end
```

**Principios:**

1. **GitHub Actions dispara el deploy.** Render NO se auto-despliega al recibir un push.
2. **Solo se despliega `main`.** Los PRs nunca disparan deploys.
3. **La base de datos se crea antes que el Web Service.** El Web Service consume la URI interna de la base.
4. **Los secretos viven en Render.** Nunca en el repositorio ni en GitHub Secrets (excepto los deploy hooks).

## Rol de ejecución de PostgreSQL en local

En Docker Compose, la aplicación se conecta con el rol `gameapi_app`, que solo
recibe permisos DML sobre las tablas de la API. El rol y sus permisos iniciales
se configuran mediante un script de inicialización de PostgreSQL.

Los scripts de `docker/initdb` se ejecutan únicamente cuando PostgreSQL crea un
volumen de datos nuevo. Para volver a ejecutarlos en local, elimina el volumen
y levanta los servicios de nuevo:

```bash
docker compose down -v && docker compose up -d
```

> Este comando elimina los datos locales de PostgreSQL.

Comprueba que el rol existe y revisa los permisos de una tabla con:

```bash
docker compose exec postgres psql -U gameapi -d gameapi -c '\du gameapi_app'
docker compose exec postgres psql -U gameapi -d gameapi -c '\dp public.users'
```

## Requisitos previos

- Cuenta en [Render](https://render.com).
- Acceso al repositorio `gameapi` en GitHub.
- `openssl` instalado localmente (para generar la clave JWT).
- `curl` y `jq` (para verificar el despliegue).

## Paso 1 — Generar la clave JWT

La clave JWT debe ser única, larga y aleatoria. Nunca uses el valor por defecto.

```bash
openssl rand -base64 48
```

Copia el valor resultante. Ejemplo de salida:

```text
7XvN3kR2pQ8yLmW9sT5bC4dF6gH1jK0mN3oP2qR5tV8wX9yZ0aB3cD6eF9gH2iJ5k
```

Guárdala en tu gestor de contraseñas del equipo. La usarás en el paso 4.

## Paso 2 — Crear la base de datos PostgreSQL

1. Ve a <https://dashboard.render.com> → **New +** → **PostgreSQL**.
2. Configura:
   - **Name:** `gameapi-db`
   - **Database:** `gameapi`
   - **User:** `gameapi`
   - **Region:** `Oregon (US West)` (o la más cercana a tu equipo)
   - **Plan:** `Free`
   - **PostgreSQL Version:** `16`
3. Click en **Create Database**.
4. Espera a que el estado cambie a **Available** (1–2 minutos).
5. Copia el **Internal Database URL** de la sección **Connections**. Se ve así:
   ```text
   postgres://gameapi:password@dpg-xxxxx-a.oregon.render.com:5432/gameapi
   ```
6. Guarda este valor. El backend lo transforma automáticamente al prefijo `postgresql+asyncpg://` (ver `PostgresSettings` en `core/config.py`).

> Nota: el Internal URL solo funciona desde dentro de la red de Render. No es accesible desde tu máquina local. Para eso existe el External URL, que puedes usar para conectarte con `psql`.

## Paso 3 — Crear el Web Service

1. En el dashboard, **New +** → **Web Service**.
2. Conecta tu repositorio `gameapi` de GitHub.
3. Configura:
   - **Name:** `gameapi`
   - **Region:** `Oregon (US West)` (debe coincidir con la DB)
   - **Branch:** `main`
   - **Runtime:** `Docker`
   - **Dockerfile Path:** `./Dockerfile`
   - **Docker Context:** `.`
   - **Plan:** `Free`
   - **Health Check Path:** `/health`
   - **Auto-Deploy:** **`No`** (crítico — GitHub Actions lo dispara)
4. Click en **Create Web Service**.

> Importante: el Web Service fallará en el primer arranque porque aún no tiene las variables de entorno. Eso es esperado. Las configuramos en el siguiente paso.

## Paso 4 — Configurar variables de entorno

En el dashboard del Web Service, ve a **Environment** y agrega las siguientes variables:

| Variable | Valor | Cómo obtenerlo |
|---|---|---|
| `POSTGRES_URI` | `postgresql://gameapi:...` | El **Internal Database URL** del paso 2 |
| `JWT_SECRET_KEY` | _(tu clave del paso 1)_ | `openssl rand -base64 48` |
| `JWT_ALGORITHM` | `HS256` | Constante |
| `JWT_ISSUER` | `GameAPI` | Constante |
| `JWT_AUDIENCE` | `GameAPI` | Constante |
| `JWT_EXPIRE_MINUTES` | `60` | Constante |
| `AUTH_COOKIE_SECURE` | `true` | Constante |
| `AUTH_COOKIE_SAMESITE` | `lax` | Constante |
| `AUTH_COOKIE_DOMAIN` | _(vacío o dominio)_ | Opcional |
| `LOG_ADMIN_EMAILS` | `admin@gameapi.local` | Equipo |
| `APP_ENV` | `production` | Constante |
| `APP_HOST` | `0.0.0.0` | Constante |
| `CORS_ORIGINS` | `https://app.example.com` | Dominio(s) de frontend |
| `RATE_LIMIT_ENABLED` | `true` | Constante |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | Constante |
| `LOG_BUFFER_SIZE` | `100` | Constante |
| `LOG_FLUSH_INTERVAL_SECONDS` | `5.0` | Constante |
| `LOG_RETENTION_DAYS` | `30` | Constante |

> **Sobre el formato de `POSTGRES_URI`**
>
> Render entrega la URL interna en formato `postgres://` o `postgresql://`
> (sin el sufijo del driver async). El backend **normaliza automáticamente**
> ese valor a `postgresql+asyncpg://` durante el arranque, por lo que puedes
> pegar la URL tal como la entrega Render sin modificarla.
>
> Si la aplicación falla con `ModuleNotFoundError: No module named 'psycopg'`,
> significa que la normalización no se aplicó. Verifica que la variable
> `POSTGRES_URI` esté configurada y que el código incluya el validador
> `_normalize_nested_uris` en `Settings`. Como alternativa, puedes añadir
> manualmente el sufijo:
>
> ```
> postgresql+asyncpg://gameapi:password@dpg-xxxxx-a/gameapi
> ```

## Paso 5 — Configurar GitHub Actions y Render deploy hook

1. En el repositorio, crea los secrets de GitHub:
   - `RENDER_DEPLOY_HOOK_API`
   - `RENDER_API_KEY`
   - `RENDER_SERVICE_ID_API`
2. En Render, copia el **Deploy Hook URL** del servicio `gameapi`.
3. Pégalo en `RENDER_DEPLOY_HOOK_API`.
4. Para el polling opcional, usa el **Render API Key** y el **Service ID** de la API de Render.
5. El workflow `.github/workflows/deploy.yml` se disparará tras `ci.yml` en `main`.

## Verificación post-despliegue

```bash
curl -fsS https://<tu-host-render>/health
```

Si la respuesta tiene `200 OK`, el servicio está arriba y listo para recibir peticiones.

## Nota sobre la región

Se mantiene `oregon` en la plantilla de infraestructura para que sea consistente con la configuración recomendada. Si tu equipo está en Latinoamérica y prefieres menor latencia, puedes cambiar la región a `ohio` o `virginia` en Render y en tu archivo `render.yaml`.
