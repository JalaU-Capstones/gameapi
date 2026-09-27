# Colecciones de cliente

Este directorio contiene las colecciones de cliente para probar la API de GameAPI manualmente desde Postman o Insomnia.

## Índice

- [¿Por qué dos colecciones?](#por-qué-dos-colecciones)
- [Postman — solo REST](#postman--solo-rest)
- [Insomnia — REST + WebSocket](#insomnia--rest--websocket)
- [Contenido del directorio](#contenido-del-directorio)
- [Flujo recomendado](#flujo-recomendado)
- [Diferencias de sintaxis](#diferencias-de-sintaxis-entre-postman-e-insomnia)
- [Solución de problemas](#solución-de-problemas)

---

## ¿Por qué dos colecciones?

La API expone dos familias de endpoints — REST (`/api/v1/*`) y WebSocket (`/api/v2/ws/*`) — pero **ninguna herramienta cubre ambos casos con la misma calidad**:

| Herramienta  | REST      | WebSocket  | Rol en este proyecto           |
|--------------|-----------|------------|--------------------------------|
| **Postman**  | Excelente | Problemático | Se usa **solo para REST**      |
| **Insomnia** | Excelente | Nativo     | Se usa para **REST + WebSocket** |

### El problema con WebSocket en Postman

Postman tiene soporte de WebSocket, pero **no convive bien con requests REST en la misma colección**:

1. Al **importar** una colección que mezcla requests HTTP y WS, Postman frecuentemente convierte los requests WS en `GET` HTTP — incluso si el JSON declara `protocolProfileBehavior.useWebSocket: true` y `url.protocol: "ws"`.
2. El resultado es el error:
   ```
   Invalid protocol: ws:
   ```
   porque Postman intenta procesar `ws://...` como una URL HTTP y rechaza el protocolo.
3. Cambiar el método manualmente a **WebSocket** en la UI funciona, pero **el cambio se pierde al reimportar** la colección, lo que rompe la reproducibilidad.
4. En algunas versiones, el soporte de WebSocket requiere plan de pago.

**Conclusión**: Postman queda relegado a las pruebas REST. Los WebSocket se prueban con Insomnia (o con `websocat` / `wscat` desde la terminal).

### Por qué Insomnia

Insomnia tiene soporte **nativo y estable** de WebSocket desde la versión 8:

- Los requests se declaran con `_type: websocket_request` en el YAML de exportación.
- Al importar, la UI muestra el botón **Connect** (no **Send**), sin ambigüedad HTTP.
- El editor de mensajes soporta formato JSON, lo que hace trivial enviar y leer el protocolo del WebSocket (`auth`, `ping`, `subscribe_game`, etc.).
- Los scripts de ciclo de vida (`afterResponseScript`) funcionan igual que en Postman.

Por eso Insomnia es la herramienta de referencia para probar **todo** el API.

---

## Postman — solo REST

**Archivo:** [`GameAPI.postman_collection.json`](./postman/GameAPI.postman_collection.json)

**Cubre:**

- Registro y login de usuarios.
- CRUD de usuarios con permisos (ownership).
- CRUD de gameplays con permisos (host / guest).

**NO cubre WebSockets** por las razones explicadas arriba. Si agregas los endpoints WS a la colección, esta se rompe al reimportar.

**Importar:**

1. Abre Postman.
2. **File → Import → Upload Files**.
3. Selecciona `GameAPI.postman_collection.json`.
4. Selecciona la colección en la barra lateral.

**Variables** (definidas en la colección; se actualizan automáticamente desde los scripts):

| Variable       | Descripción                              | Set por                        |
|----------------|------------------------------------------|--------------------------------|
| `baseUrl`      | Host + puerto (sin esquema)              | Usuario                        |
| `token`        | JWT para endpoints autenticados          | Script de **Login**            |
| `userId`       | UUID del usuario actual                  | Script de **Register / Login** |
| `gameplayId`   | UUID del último gameplay creado          | Script de **Create gameplay**  |
| `testEmail`    | Email para login                         | Usuario                        |
| `testPassword` | Password para login                      | Usuario                        |

**Cada request tiene documentación completa** en el panel **Documentation** (icono de documento en el panel derecho de Postman). También los folders **Users** y **Gameplays** tienen documentación general.

---

## Insomnia — REST + WebSocket

**Archivo:** [`GameAPI.insomnia.yaml`](./insomnia/GameAPI.insomnia.yaml)

**Cubre:**

- Todo lo de la colección Postman (REST).
- Los dos endpoints WebSocket: `/api/v2/ws/presence` y `/api/v2/ws/gameplays`.

**Importar:**

1. Abre Insomnia.
2. **Application → Preferences → Data → Import Data → From File**.
3. Selecciona `GameAPI.insomnia.yaml`.
4. Activa el entorno **Local** en el desplegable superior izquierdo.

**Variables del entorno `Local`:**

| Variable       | Descripción                              | Set por                        |
|----------------|------------------------------------------|--------------------------------|
| `baseUrl`      | Host + puerto (sin esquema)              | Usuario                        |
| `token`        | JWT para endpoints autenticados          | Script de **Login**            |
| `userId`       | UUID del usuario actual                  | Script de **Register / Login** |
| `gameplayId`   | UUID del último gameplay creado          | Script de **Create gameplay**  |
| `testEmail`    | Email para login                         | Usuario                        |
| `testPassword` | Password para login                      | Usuario                        |

**Cada request tiene documentación completa** en el panel **Docs** (icono de libro en el panel central de Insomnia). Los folders y el workspace también están documentados.

---

## Contenido del directorio

```
.docs/collections/
├── README.md                                 # Este archivo
├── postman/GameAPI.postman_collection.json    # Colección Postman (solo REST)
└── insomnia/GameAPI.insomnia.yaml              # Colección Insomnia (REST + WebSocket)
```

---

## Flujo recomendado

Para cualquiera de las dos herramientas, el orden de ejecución es el mismo:

1. **Users → Register user** — crea la cuenta; guarda `userId` y `testEmail`.
2. **Users → Login** — obtiene el JWT; guarda `token` y `userId`.
3. **Gameplays → Create gameplay** — crea una partida; guarda `gameplayId`.
4. A partir de aquí puedes probar cualquier endpoint REST.

> Los scripts de respuesta son los que rellenan las variables. Si ejecutas requests fuera de este orden, verás `{{userId}}` o `{{token}}` vacíos.

### Probar WebSocket (solo Insomnia)

1. Abre **WebSocket (v2) → Presence WS** o **Gameplays WS**.
2. Pulsa **Connect**.
3. Envía inmediatamente (el servidor cierra la conexión si tardas más de unos segundos):
   ```json
   {"event":"auth","payload":{"token":"{{ _.token }}"}}
   ```
4. Espera la respuesta:
   ```json
   {"event":"auth_ok","payload":{"user_id":"..."}}
   ```
5. A partir de ahí puedes enviar `ping`, `list_online_users`, `subscribe_game`, `broadcast_to_game`, etc.

### Probar WebSocket sin Insomnia

Si prefieres la terminal:

```bash
# Con websocat (recomendado, interactivo)
websocat -t ws://localhost:8080/api/v2/ws/presence

# Con wscat (Node.js)
npx wscat -c ws://localhost:8080/api/v2/ws/presence
```

Ambas herramientas te dejan pegar el mensaje de `auth` en la sesión interactiva y ver las respuestas.

---

## Diferencias de sintaxis entre Postman e Insomnia

Si editas ambos archivos, ten presente que la sintaxis de plantillas y scripts cambia:

| Concepto                    | Postman                              | Insomnia                            |
|-----------------------------|--------------------------------------|-------------------------------------|
| Interpolación de variables  | `{{variable}}`                       | `{{ _.variable }}`                  |
| Asignar variable            | `pm.collectionVariables.set("x", v)` | `insomnia.environment.set("x", v)`  |
| Leer respuesta              | `pm.response.json()`                 | `insomnia.response.json()`          |
| Código HTTP                 | `pm.response.code`                   | `insomnia.response.code`            |
| Aserciones                  | `pm.test(...)`                       | No nativo (usa `console.log`)       |

---

## Solución de problemas

### Postman muestra `Invalid protocol: ws:`

**Síntoma**: intentaste agregar un request WebSocket a la colección Postman y ahora falla.

**Solución**: **no agregues WebSockets a Postman**. Usa Insomnia para eso. Ver [El problema con WebSocket en Postman](#el-problema-con-websocket-en-postman).

### Insomnia cierra la conexión con `auth_timeout`

**Síntoma**: te conectas al WebSocket pero la conexión se cierra a los pocos segundos sin respuesta.

**Causa**: el servidor exige que el **primer mensaje** sea `auth`, y cierra la conexión si tardas más de unos segundos.

**Solución**: conecta y envía el mensaje `auth` **inmediatamente**. Ten el JSON listo en el editor antes de pulsar **Connect**. Si necesitas más margen, sube el timeout en el servidor WebSocket.

### El token expira durante la sesión

Los JWT duran 60 minutos por defecto (`JWT_EXPIRE_MINUTES`). Si recibes `401`, vuelve a ejecutar **Login** para refrescar `{{token}}` (Postman) o `{{ _.token }}` (Insomnia).

### `websocat: WebSocketError: I/O failure` en modo interactivo

**Síntoma**: al ejecutar `websocat -t ws://...` en la terminal, falla con `I/O failure`.

**Causa**: websocat cambia la terminal a modo raw y algunos shells/terminales no lo manejan bien.

**Solución**: envuelve con `rlwrap` (`rlwrap websocat -t ws://...`) o usa un pipe con `begin...end` + `sleep` para enviar varios mensajes sin modo interactivo.

### `curl: option --ws: is unknown`

**Causa**: tu versión de curl es anterior a 7.86 (octubre 2022), que es cuando se añadió soporte de WebSocket.

**Solución**: actualiza curl (`sudo apt install --only-upgrade curl`) o simplemente usa `websocat`/`wscat`. Curl además solo permite enviar **un** frame, así que no sirve para flujos interactivos de todos modos.

---

## Referencias

- [Postman — WebSocket requests](https://learning.postman.com/docs/sending-requests/websocket/websocket-overview/)
- [Insomnia — WebSockets](https://docs.insomnia.rest/insomnia/websockets)
- [websocat](https://github.com/vi/websocat)
- [wscat](https://github.com/websockets/wscat)
