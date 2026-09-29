# Client Collections

This directory contains client collections for manually testing the GameAPI with Postman or Insomnia.

## Contents

- [Why two collections?](#why-two-collections)
- [Postman — REST only](#postman--rest-only)
- [Insomnia — REST + WebSocket](#insomnia--rest--websocket)
- [Directory contents](#directory-contents)
- [Recommended flow](#recommended-flow)
- [Syntax differences between Postman and Insomnia](#syntax-differences-between-postman-and-insomnia)
- [Troubleshooting](#troubleshooting)
- [References](#references)

---

## Why two collections?

The API exposes two endpoint families — REST (`/api/v1/*`) and WebSocket (`/api/v2/ws/*`) — but **neither tool covers both equally well**:

| Tool | REST | WebSocket | Role in this project |
|------|------|-----------|----------------------|
| **Postman** | Excellent | Problematic | Used for **REST only** |
| **Insomnia** | Excellent | Native | Used for **REST + WebSocket** |

### The problem with WebSocket in Postman

Postman supports WebSocket, but **HTTP requests and WebSocket requests do not coexist reliably in the same collection**:

1. When you **import** a collection that mixes HTTP and WebSocket requests, Postman often converts WebSocket requests to HTTP `GET` requests, even if the JSON declares `protocolProfileBehavior.useWebSocket: true` and `url.protocol: "ws"`.
2. The result is this error:
   ```
   Invalid protocol: ws:
   ```
   Postman attempts to process `ws://...` as an HTTP URL and rejects the protocol.
3. Changing the method manually to **WebSocket** in the UI works, but **the change is lost when the collection is reimported**, breaking reproducibility.
4. In some versions, WebSocket support requires a paid plan.

**Conclusion**: Postman is limited to REST testing. Use Insomnia (or `websocat` / `wscat` from the terminal) to test WebSockets.

### Why Insomnia

Insomnia has had **native, stable** WebSocket support since version 8:

- Requests use `_type: websocket_request` in the exported YAML.
- After import, the UI shows a **Connect** button (not **Send**), with no HTTP ambiguity.
- The message editor supports JSON, making it easy to send and inspect the WebSocket protocol (`auth`, `ping`, `subscribe_game`, etc.).
- Lifecycle scripts (`afterResponseScript`) work similarly to Postman.

For these reasons, Insomnia is the reference tool for testing the **entire** API.

---

## Postman — REST only

**File:** [`GameAPI.postman_collection.json`](./postman/GameAPI.postman_collection.json)

**Includes:**

- User registration and login.
- User CRUD operations with ownership permissions.
- Gameplay CRUD operations with host / guest permissions.

**WebSockets are not included** for the reasons described above. Adding WebSocket endpoints to the collection can make it fail after reimport.

**Import:**

1. Open Postman.
2. Select **File → Import → Upload Files**.
3. Choose `GameAPI.postman_collection.json`.
4. Select the collection in the sidebar.

**Variables** (defined in the collection and updated automatically by scripts):

| Variable | Description | Set by |
|----------|-------------|--------|
| `baseUrl` | Host and port (no scheme) | User |
| `token` | JWT for authenticated endpoints | **Login** script |
| `userId` | Current user's UUID | **Register / Login** script |
| `gameplayId` | UUID of the most recently created gameplay | **Create gameplay** script |
| `testEmail` | Email used for login | User |
| `testPassword` | Password used for login | User |

**Every request has full documentation** in Postman's **Documentation** panel (document icon in the right panel). The **Users** and **Gameplays** folders also include general documentation.

---

## Insomnia — REST + WebSocket

**File:** [`GameAPI.insomnia.yaml`](./insomnia/GameAPI.insomnia.yaml)

**Includes:**

- All REST requests from the Postman collection.
- The v2 auth endpoints, including the HttpOnly cookie flow.
- Both WebSocket endpoints: `/api/v2/ws/presence` and `/api/v2/ws/gameplays`.

**Import:**

1. Open Insomnia.
2. Select **Application → Preferences → Data → Import Data → From File**.
3. Choose `GameAPI.insomnia.yaml`.
4. Select the **Local** environment from the dropdown in the upper-left corner.

**`Local` environment variables:**

| Variable | Description | Set by |
|----------|-------------|--------|
| `baseUrl` | Host and port (no scheme) | User |
| `token` | JWT for authenticated endpoints and WebSockets | **Login** script |
| `userId` | Current user's UUID | **Register / Login** script |
| `gameplayId` | UUID of the most recently created gameplay | **Create gameplay** script |
| `testEmail` | Email used for login | User |
| `testPassword` | Password used for login | User |
| `access_token` | Access token returned by v2 login | **Login (v2)** script |
| `refresh_token` | Refresh token captured from the v2 login cookie | **Login (v2)** script |

**Every request has full documentation** in Insomnia's **Docs** panel (book icon in the center panel). The folders and workspace are documented as well.

---

## Directory contents

```
.docs/collections/
├── README.md                                      # This file
├── postman/GameAPI.postman_collection.json         # Postman collection (REST only)
└── insomnia/GameAPI.insomnia.yaml                  # Insomnia collection (REST + WebSocket)
```

---

## Recommended flow

The execution order is the same for either tool:

1. **Users → Register user** — creates the account and stores `userId` and `testEmail`.
2. **Users → Login** — obtains a JWT and stores `token` and `userId`.
3. **Gameplays → Create gameplay** — creates a gameplay and stores `gameplayId`.
4. Continue with any REST endpoint.

> Response scripts populate the variables. If you run requests out of order, `{{userId}}` or `{{token}}` may be empty.

### Test WebSocket (Insomnia only)

1. Open **WebSocket (v2) → Presence WS** or **Gameplays WS**.
2. Click **Connect**.
3. Send this immediately (the server closes the connection if you wait more than a few seconds):
   ```json
   {"event":"auth","payload":{"token":"{{ _.token }}"}}
   ```
4. Wait for the response:
   ```json
   {"event":"auth_ok","payload":{"user_id":"..."}}
   ```
5. You can then send `ping`, `list_online_users`, `subscribe_game`, `broadcast_to_game`, and other events.

### Test WebSocket without Insomnia

From a terminal, use either:

```bash
# With websocat (recommended, interactive)
websocat -t ws://localhost:8080/api/v2/ws/presence

# With wscat (Node.js)
npx wscat -c ws://localhost:8080/api/v2/ws/presence
```

Both tools let you paste the `auth` message into the interactive session and view the responses.

---

## Syntax differences between Postman and Insomnia

If you edit both files, keep in mind that template and script syntax differs:

| Concept | Postman | Insomnia |
|---------|---------|----------|
| Variable interpolation | `{{variable}}` | `{{ _.variable }}` |
| Set a variable | `pm.collectionVariables.set("x", v)` | `insomnia.environment.set("x", v)` |
| Read a response | `pm.response.json()` | `insomnia.response.json()` |
| HTTP status code | `pm.response.code` | `insomnia.response.code` |
| Assertions | `pm.test(...)` | Not built in (use `console.log`) |

---

## Troubleshooting

### Postman shows `Invalid protocol: ws:`

**Symptom**: You tried adding a WebSocket request to the Postman collection, and it now fails.

**Solution**: **Do not add WebSockets to Postman**. Use Insomnia instead. See [The problem with WebSocket in Postman](#the-problem-with-websocket-in-postman).

### Insomnia closes the connection with `auth_timeout`

**Symptom**: You connect to the WebSocket, but it closes after a few seconds without responding.

**Cause**: The server requires `auth` as the **first message** and closes the connection if you wait too long.

**Solution**: Connect and send the `auth` message **immediately**. Have the JSON ready in the editor before clicking **Connect**. Increase the server WebSocket timeout if you need more time.

### The token expires during the session

JWTs last 60 minutes by default (`JWT_EXPIRE_MINUTES`). If you receive `401`, run **Login** again to refresh `{{token}}` (Postman) or `{{ _.token }}` (Insomnia).

### `websocat: WebSocketError: I/O failure` in interactive mode

**Symptom**: Running `websocat -t ws://...` in the terminal fails with `I/O failure`.

**Cause**: websocat switches the terminal to raw mode, which some shells and terminals do not handle well.

**Solution**: Wrap it with `rlwrap` (`rlwrap websocat -t ws://...`) or use a pipe with `begin...end` and `sleep` to send multiple messages without interactive mode.

### `curl: option --ws: is unknown`

**Cause**: Your curl version predates 7.86 (October 2022), when WebSocket support was added.

**Solution**: Update curl (`sudo apt install --only-upgrade curl`) or use `websocat` / `wscat`. Curl also only allows sending **one** frame, so it is not suitable for interactive flows.

---

## References

- [Postman — WebSocket requests](https://learning.postman.com/docs/sending-requests/websocket/websocket-overview/)
- [Insomnia — WebSockets](https://docs.insomnia.rest/insomnia/websockets)
- [websocat](https://github.com/vi/websocat)
- [wscat](https://github.com/websockets/wscat)
