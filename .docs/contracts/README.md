# Contratos de API

Este directorio contiene los contratos formales de la API en formato legible por máquinas. Son la fuente de verdad para todos los clientes (frontend, herramientas de testing, scripts).

## Contenido

```text
.docs/contracts/
├── README.md           # Este archivo
├── openapi/
│   └── openapi.json    # Contrato REST (v1 + v2)
└── asyncapi/
    └── asyncapi.json   # Contrato WebSocket (v2)
```

## ¿Por qué?

Los contratos viven en el repositorio por tres razones:

1. Accesibles sin servidor. Cualquier persona puede leerlos sin levantar la API.
2. Diffables en Pull Requests. Cambios al contrato aparecen como diffs claros y revisables.
3. Inmutabilidad. Son la referencia oficial; cualquier cambio pasa por revisión de código antes de mergear.

## OpenAPI (REST)

Generado automáticamente desde el código Python con FastAPI. Cubre:

- v1 — contrato congelado (compatibilidad con el legacy C#).
- v2 — contrato activo.
- Auth (`/api/v2/auth/*`) — login, register, refresh, logout, me.
- Users, Gameplays, Logs.

### Regenerar

Después de cualquier cambio en los endpoints REST:

```bash
make openapi-export
```

El script importa la app FastAPI y vuelca el schema sin necesidad de levantar un servidor. Siempre regenera el contrato antes de abrir un MR que modifique endpoints. Los pipelines verifican que el archivo commiteado coincide con el generado.

### Validar

```bash
python -c "import json; json.load(open('.docs/contracts/openapi/openapi.json'))"
```

## AsyncAPI (WebSocket)

Contrato manual para los endpoints WebSocket. Cubre dos canales:

- `/api/v2/ws/gameplays` — eventos de partida (invitaciones, turnos, victorias).
- `/api/v2/ws/presence` — presencia de usuarios (online/offline).

### Regenerar

A diferencia de OpenAPI, este archivo se mantiene a mano. Cuando agregues o modifiques un evento WebSocket:

1. Actualiza el handler en `src/gameapi/api/v2/ws/*.py`.
2. Actualiza el schema en `src/gameapi/schemas/ws_events.py` si aplica.
3. Edita `.docs/contracts/asyncapi/asyncapi.json` para reflejar el cambio.
4. Corre los tests.

### Validar

```bash
make asyncapi-validate
```

Usa el AsyncAPI CLI para verificar que el documento cumple con la especificación 3.0.0.

## Versionado

| Componente | Versión | Estado |
|---|---|---|
| REST v1 | 1.0.0 | 🔒 Congelado |
| REST v2 | 2.0.0 | 🟢 Activo |
| WebSocket v2 | 2.0.0 | 🟢 Activo |

Política de cambios:

- v1: solo se permiten ajustes de seguridad documentados (ej. endurecer auth). Cambios de paths o shapes están prohibidos.
- v2: evolución libre mientras no rompa clientes existentes. Cambios breaking requieren un bump a v3.

## Herramientas

### Ver el contrato OpenAPI renderizado

Pégalo en <https://editor.swagger.io> o usa Redoc:

```bash
npx @redocly/cli preview-docs .docs/contracts/openapi/openapi.json
```

### Ver el contrato AsyncAPI renderizado

Pégalo en <https://studio.asyncapi.com> o usa el CLI:

```bash
npx @asyncapi/cli start studio .docs/contracts/asyncapi/asyncapi.json
```

### Validar ambos contratos en CI

Los pipelines verifican:

1. `openapi.json` generado coincide con el commiteado.
2. `asyncapi.json` es válido según AsyncAPI 3.0.0.

Si falla cualquiera, el MR no se puede mergear hasta resolver.
