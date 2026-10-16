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

En el dashboard del Web Service, ve a **Environment** y agrega todas las variables que usa la app. En Render Free, el servicio se suspende tras 15 minutos de inactividad, la memoria está limitada a 512 MB, la CPU a 0.1 y la base de datos tiene cuotas pequeñas. Por eso conviene mantener los valores conservadores, no usar Redis y evitar cachés o logs demasiado agresivos.

> La app consume estas variables en `src/gameapi/core/config.py` y en `.env.example`. La tabla siguiente resume los valores recomendados para una instancia en Render Free.

| Variable | Valor recomendado | Racional |
|---|---|---|
| `POSTGRES_URI` | `postgresql://gameapi:...` | Usa la URL interna de la base de datos de Render. La app normaliza `postgres://` y `postgresql://` a `postgresql+asyncpg://` automáticamente. |
| `POSTGRES_USER` | `gameapi` | Usuario de la base de datos creada en Render. |
| `POSTGRES_PASSWORD` | _valor secreto del rol_ | Debe venir de la DB creada en Render; no lo guardes en el repositorio. |
| `POSTGRES_DB` | `gameapi` | Nombre de la base de datos. |
| `GAMEAPI_APP_PASSWORD` | `gameapi_app_dev` o valor equivalente | Solo se usa al inicializar PostgreSQL local en Docker. En Render no es necesario a menos que repitas un entorno local. |
| `JWT_SECRET_KEY` | `openssl rand -base64 48` | Debe ser único y largo. En producción no se acepta el valor por defecto. |
| `JWT_ALGORITHM` | `HS256` | Algoritmo estándar para JWT en este proyecto. |
| `JWT_ISSUER` | `GameAPI` | Identificador del emisor utilizado por la app. |
| `JWT_AUDIENCE` | `GameAPI` | Identificador del público esperado por la app. |
| `JWT_EXPIRE_MINUTES` | `60` | Vale para sesiones de acceso razonables sin forzar re-login. |
| `AUTH_ACCESS_COOKIE_NAME` | `gameapi_at` | Nombre del cookie de acceso; mantén el valor por defecto para que el frontend y la API coincidan. |
| `AUTH_REFRESH_COOKIE_NAME` | `gameapi_rt` | Nombre del cookie de refresh; debe mantenerse estable. |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Reduce la ventana de robo de tokens y respeta la experiencia de sesión web. |
| `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Balance razonable para sesiones persistentes en producción. |
| `AUTH_COOKIE_SECURE` | `true` | Render usa HTTPS; esta opción evita cookies sobre texto plano. |
| `AUTH_COOKIE_SAMESITE` | `lax` | Es el valor más seguro y compatible para un frontend en dominio separado. |
| `AUTH_COOKIE_DOMAIN` | `""` o vacío | En Render, normalmente no necesitas fijar este valor salvo un dominio específico. |
| `AUTH_REFRESH_COOKIE_PATH` | `/api/v2/auth` | Coincide con la ruta real de refresh en la API. |
| `AUTH_ACCESS_COOKIE_PATH` | `/` | Permite que la sesión principal se use en toda la app. |
| `INVITATION_PENDING_TTL_SECONDS` | `60` | Mantiene el flujo de invitación vivo pero evita esperas indefinidas. |
| `INVITATION_QUEUED_TTL_SECONDS` | `300` | Da margen para que el invitado responda sin que la invitación expire demasiado pronto. |
| `INVITATION_EXPIRY_INTERVAL_SECONDS` | `10.0` | Tarea periódica de expiración ligera; es suficiente para el plan gratuito. |
| `INVITATION_QUEUED_EXPIRY_INTERVAL_SECONDS` | `30.0` | Reduce la frecuencia de comprobación para ahorrar CPU. |
| `ABANDON_GRACE_SECONDS` | `5.0` | Aporta un pequeño margen para manejar desconexiones pausadas sin penalizar a jugadores activos. |
| `INVITATION_PAIR_MAX_ATTEMPTS` | `3` | Limita los reintentos por par de usuarios. |
| `INVITATION_PAIR_WINDOW_SECONDS` | `180` | Ventana corta para evitar reintentos abusivos sin bloquear tráfico normal. |
| `CHAT_RATE_MAX_MESSAGES` | `10` | Evita spam en la sala de chat con una tasa conservadora. |
| `CHAT_RATE_WINDOW_SECONDS` | `10.0` | Ventana corta y útil para detectar abuso; no penaliza mucho el uso normal. |
| `CHAT_RATE_BLOCK_SECONDS` | `30.0` | Penalización razonable para evitar reintentos agresivos. |
| `APP_ENV` | `production` | Debe ser `production` para activar validaciones de seguridad y evitar valores de desarrollo. |
| `APP_HOST` | `0.0.0.0` | Render inyecta el host real; este valor es el estándar para servicios HTTP. |
| `APP_PORT` | `8080` | Puerto esperado por el contenedor y la configuración del servicio. |
| `CORS_ORIGINS` | `https://app.example.com` | En producción, evita `*` porque los cookies con `SameSite=lax` y credenciales requieren orígenes explícitos. |
| `LOG_BUFFER_SIZE` | `100` | Mantiene el lote de logs pequeño para no saturar memoria ni CPU. |
| `LOG_FLUSH_INTERVAL_SECONDS` | `5.0` | Frecuencia suficiente para evitar pérdida masiva de logs sin forzar I/O excesivo. |
| `LOG_RETENTION_DAYS` | `30` | Es un valor prudente para la cuota de almacenamiento de la base de datos. |
| `LOG_QUEUE_MAXSIZE` | `1000` | Evita que la cola de eventos crezca sin control cuando el servicio está inactivo. |
| `LOG_ADMIN_EMAILS` | `admin@gameapi.local` | Lista de administradores para consulta de logs; en prod conviene usar correos reales del equipo. |
| `RATE_LIMIT_ENABLED` | `true` | Habilita protección contra abuso en un servicio público. |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | En Render Free no hay Redis. `memory://` es la elección correcta y evita fallos de infraestructura. |
| `RATE_LIMIT_LOGIN` | `5/minute` | Límite razonable para prevenir fuerza bruta. |
| `RATE_LIMIT_REGISTER` | `3/minute` | Limita alta frecuencia de creación de cuentas. |
| `RATE_LIMIT_REFRESH` | `10/minute` | Mantiene las rotaciones de token bajo control. |
| `RATE_LIMIT_ANONYMOUS_DEFAULT` | `60/minute` | Suficiente para clientes normales sin permitir abuso extremo. |
| `RATE_LIMIT_AUTHENTICATED_DEFAULT` | `60/minute` | Valor conservador para usuarios autenticados. |
| `RATE_LIMIT_AUTH_ME` | `60/minute` | Límite de la consulta de perfil; evita abuso de polling. |
| `RATE_LIMIT_LOGS_ME` | `30/minute` | Reduce la presión sobre el endpoint de logs personales. |
| `RATE_LIMIT_LOGS_ADMIN` | `300/minute` | Permite a administradores consultar logs sin abrir una ventana demasiado amplia. |
| `RATE_LIMIT_CREATE_GAME` | `5/minute` | Compatibiliza la creación de partidas con los límites de invitación y evita spikes de carga. |
| `RATE_LIMIT_WS_HANDSHAKE` | `10/minute` | Protege los WebSockets de conexiones repetitivas y rotativas. |
| `RATE_LIMIT_SESSION_TAKEOVER` | `3/minute` | Limita intentos de takeover de sesión. |

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
> postgres://<user>:<password>@<host>:5432/<db>
> ```
>
> y dejar que el código lo convierta a `postgresql+asyncpg://...`.

> **Caveats de Render Free**
>
> - El servicio entra en suspensión tras 15 minutos de inactividad; la primera petición puede tardar 30–60 segundos.
> - La memoria máxima es 512 MB y la CPU 0.1, así que mantén los buffers y logs pequeños.
> - No existe Redis en el plan gratuito; usa `RATE_LIMIT_STORAGE_URI=memory://` y no dependas de un broker externo.
> - La base de datos PostgreSQL tiene una cuota de almacenamiento limitada; revisa el tamaño de `logs` y el tamaño de tablas si el servicio tarda en crecer.
> - El `cold start` obliga a mantener tiempos de expiración cortos y límites de tarifa razonables para evitar que la primera petición falle por saturación.

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
