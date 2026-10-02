# Limitación de tasa (rate limiting)

## Objetivo

La API protege los endpoints más sensibles y costosos con límites de tasa para evitar abuso, fuerza bruta y consumo accidental masivo de recursos. El enfoque aplica una política por ruta y por cliente, con reglas distintas para tráfico anónimo y autenticado.

## Estrategia de clave y routing

La capa central de rate limiting vive en `src/gameapi/core/rate_limit.py` y usa SlowAPI con una función de clave jerárquica:

1. Si la ruta es anónima por diseño (login, registro, refresh o login v1), se usa la IP remota.
2. Si hay JWT válido en el header `Authorization: Bearer ...`, se usa `user:{sub}`.
3. Si hay un cookie `gameapi_at` válido, se usa `user:{sub}` para clientes web.
4. Si no hay autenticación válida, se usa la IP remota como clave.

Esto evita que un usuario autenticado comparta el límite con otros clientes y al mismo tiempo no penaliza los flujos de registro o login anónimos.

## Mecanismo de implementación

La app define un wrapper tipado alrededor del decorador `slowapi.Limiter.limit(...)` para evitar los errores de strict mypy sin silenciar warnings globales. La función central es `rate_limit(limit_value: str)` en `src/gameapi/core/rate_limit.py`.

La idea es simple:

- mantenemos un único punto de integración con SlowAPI;
- los routers usan `@rate_limit(settings.rate_limit.*)`;
- la meta es preservar el tipo del callable original para mypy strict sin `# type: ignore`.

## Límites por tier

Los valores actuales se configuran desde `.env` y se exponen en `gameapi.core.config.RateLimitSettings`:

| Tier | Valor por defecto | Uso |
|---|---:|---|
| `anonymous_default` | `60/minute` | rutas públicas no autenticadas |
| `login` | `5/minute` | login y autenticación |
| `register_limit` | `3/minute` | registro de usuarios |
| `refresh` | `10/minute` | renovación de refresh token |
| `authenticated_default` | `60/minute` | endpoints autenticados por defecto |
| `auth_me` | `60/minute` | consulta del perfil |
| `logs_me` | `30/minute` | logs del usuario |
| `logs_admin` | `300/minute` | logs administrativos |
| `ws_handshake` | `10/minute` | handshakes WebSocket |

Importante: los límites por usuario se aplican por `sub` del JWT y no por correo electrónico ni por una identidad global no verificable. Esto reduce errores al mantener una clave estable para la sesión autenticada.

## Suposiciones de almacenamiento

La configuración usa por defecto `memory://` en desarrollo local y pruebas. Esto es suficiente para el entorno de la aplicación actual, pero no es una solución de producción compartida ni distribuida. En producción o en un cluster multi-instancia, se recomienda cambiar la capa de almacenamiento de SlowAPI a Redis o una backend compartida para que los contadores sostengan el mismo estado a través de varios procesos.

## Comportamiento de errores

Cuando se excede el límite, la API responde con HTTP 429 y un cuerpo homogéneo:

```json
{"message": "Too many requests. Please slow down."}
```

La respuesta incluye también cabeceras de rate limit cuando SlowAPI las inyecta en la request. Esto mantiene un patrón consistente entre clientes REST y scripts de automatización.

## Recomendaciones para frontend

- Mostrar una UI de cooldown cuando el backend responde 429.
- Si el cliente usa JWT en navegador, enviar el token en el header o cookie equivalente y no reutilizar el mismo token para ataques de fuerza bruta.
- Para clientes con varios tabs o polling continuo, respetar el `Retry-After` si está disponible.
- No intentar reintentos infinitos en endpoints protegidos por límites agresivos.

## Variables de entorno relevantes

```env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_STORAGE_URI=memory://
RATE_LIMIT_ANONYMOUS_DEFAULT=60/minute
RATE_LIMIT_AUTHENTICATED_DEFAULT=60/minute
RATE_LIMIT_LOGIN=5/minute
RATE_LIMIT_REGISTER=3/minute
RATE_LIMIT_REFRESH=10/minute
RATE_LIMIT_AUTH_ME=60/minute
RATE_LIMIT_LOGS_ME=30/minute
RATE_LIMIT_LOGS_ADMIN=300/minute
RATE_LIMIT_WS_HANDSHAKE=10/minute
```

## Iteraciones futuras

- Migrar el almacenamiento compartido a Redis para clusters multi-node.
- Separar límites por rol o nivel de usuario cuando exista un modelo de permisos formal.
- Añadir métricas y observabilidad (conteos de 429, picos por endpoint, capacidad de alertas).
- Definir una política explícita para rutas que deben ser exempt o usar un bucket más estricto.

El comportamiento actual es conservador y suficientemente defensivo para una API que atiende usuarios, sesiones y WebSockets con lógica sensible.
