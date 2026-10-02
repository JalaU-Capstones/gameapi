from __future__ import annotations

from httpx import AsyncClient

from gameapi.api.v2.ws.auth import authenticate_websocket
from gameapi.core.config import settings


async def _register_user(client: AsyncClient, *, email: str, name: str = "Rate Limit User") -> str:
    response = await client.post(
        "/api/v2/auth/register",
        json={"name": name, "email": email, "password": "password123"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


async def _login_v1_user(client: AsyncClient, *, email: str, password: str = "password123") -> str:
    response = await client.post(
        "/api/v1/users/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


async def test_login_returns_429_after_5_attempts(client: AsyncClient) -> None:
    payload = {"email": "rate-login@example.com", "password": "wrong-password"}

    for index in range(6):
        response = await client.post("/api/v2/auth/login", json=payload)
        if index < 5:
            assert response.status_code == 401, response.text
        else:
            assert response.status_code == 429, response.text
            assert response.json() == {"message": "Too many requests. Please slow down."}
            assert response.headers.get("Retry-After") is not None


async def test_login_rate_limit_headers_are_present(client: AsyncClient) -> None:
    payload = {"email": "rate-headers@example.com", "password": "wrong-password"}

    for _ in range(5):
        response = await client.post("/api/v2/auth/login", json=payload)
        assert response.status_code == 401, response.text

    response = await client.post("/api/v2/auth/login", json=payload)
    assert response.status_code == 429, response.text
    assert response.headers.get("X-RateLimit-Limit") is not None
    assert response.headers.get("X-RateLimit-Remaining") is not None
    assert response.headers.get("X-RateLimit-Reset") is not None


async def test_register_returns_429_after_3_attempts(client: AsyncClient) -> None:
    for index in range(4):
        response = await client.post(
            "/api/v2/auth/register",
            json={
                "name": f"Rate Limit {index}",
                "email": f"rate-register-{index}@example.com",
                "password": "password123",
            },
        )
        if index < 3:
            assert response.status_code == 201, response.text
        else:
            assert response.status_code == 429, response.text
            assert response.json() == {"message": "Too many requests. Please slow down."}


async def test_refresh_returns_429_after_10_attempts(client: AsyncClient) -> None:
    for index in range(11):
        client.cookies.clear()
        client.cookies.set(
            settings.auth.refresh_cookie_name,
            "not-a-valid-refresh-token",
            path=settings.auth.refresh_cookie_path,
        )
        response = await client.post("/api/v2/auth/refresh")
        if index < 10:
            assert response.status_code == 401, response.text
        else:
            assert response.status_code == 429, response.text
            assert response.json() == {"message": "Too many requests. Please slow down."}
        client.cookies.clear()


async def test_authenticated_users_have_separate_limits(client: AsyncClient) -> None:
    token_a = await _register_user(client, email="user-a@example.com", name="User A")
    token_b = await _register_user(client, email="user-b@example.com", name="User B")

    for _ in range(60):
        response = await client.get(
            "/api/v2/auth/me",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert response.status_code == 200, response.text

    response = await client.get(
        "/api/v2/auth/me",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 429, response.text

    response = await client.get(
        "/api/v2/auth/me",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 200, response.text


async def test_logs_me_returns_429_after_30_requests(client: AsyncClient) -> None:
    token = await _register_user(client, email="logs-me@example.com", name="Logs Me")

    for index in range(31):
        response = await client.get(
            "/api/v2/logs/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        if index < 30:
            assert response.status_code == 200, response.text
        else:
            assert response.status_code == 429, response.text


async def test_logs_admin_returns_429_after_300_requests(client: AsyncClient, monkeypatch) -> None:
    token = await _register_user(client, email="logs-admin@example.com", name="Logs Admin")
    monkeypatch.setattr(settings.log, "admin_emails", ["logs-admin@example.com"])

    for index in range(301):
        response = await client.get(
            "/api/v2/logs",
            headers={"Authorization": f"Bearer {token}"},
        )
        if index < 300:
            assert response.status_code == 200, response.text
        else:
            assert response.status_code == 429, response.text


async def test_health_is_exempt_from_rate_limit(client: AsyncClient) -> None:
    for _ in range(100):
        response = await client.get("/health")
        assert response.status_code == 200, response.text
        assert response.json() == {"status": "ok"}


async def test_429_response_matches_api_error_shape(client: AsyncClient) -> None:
    payload = {"email": "shape@example.com", "password": "wrong"}
    for _ in range(5):
        response = await client.post("/api/v2/auth/login", json=payload)
        assert response.status_code == 401, response.text

    response = await client.post("/api/v2/auth/login", json=payload)
    assert response.status_code == 429, response.text
    assert response.json() == {"message": "Too many requests. Please slow down."}


async def test_v1_login_rate_limited(client: AsyncClient) -> None:
    payload = {"email": "rate-v1-login@example.com", "password": "wrong-password"}

    for index in range(6):
        response = await client.post("/api/v1/users/login", json=payload)
        if index < 5:
            assert response.status_code == 401, response.text
        else:
            assert response.status_code == 429, response.text
            assert response.json() == {"message": "Too many requests. Please slow down."}


async def test_v1_register_rate_limited(client: AsyncClient) -> None:
    for index in range(4):
        response = await client.post(
            "/api/v1/users",
            json={
                "name": f"V1 Rate Limit {index}",
                "email": f"v1-rate-register-{index}@example.com",
                "password": "password123",
            },
        )
        if index < 3:
            assert response.status_code == 201, response.text
        else:
            assert response.status_code == 429, response.text
            assert response.json() == {"message": "Too many requests. Please slow down."}


async def test_v1_list_users_rate_limited(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "V1 List Rate User",
            "email": "v1-list-rate@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 201, response.text
    token = await _login_v1_user(client, email="v1-list-rate@example.com")

    for index in range(61):
        response = await client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        if index < 60:
            assert response.status_code == 200, response.text
        else:
            assert response.status_code == 429, response.text
            assert response.json() == {"message": "Too many requests. Please slow down."}


async def test_ws_handshake_returns_4429_after_10_attempts(client: AsyncClient) -> None:
    token = await _register_user(client, email="ws@example.com", name="WS User")

    class FakeSocket:
        def __init__(self, auth_token: str) -> None:
            self.auth_token = auth_token
            self.sent: list[dict] = []
            self.closed = False
            self.close_code: int | None = None
            self.close_reason: str | None = None

        async def accept(self) -> None:
            return None

        async def receive_json(self):
            return {"event": "auth", "payload": {"token": self.auth_token}}

        async def send_json(self, payload):
            self.sent.append(payload)

        async def close(self, code: int | None = None, reason: str | None = None) -> None:
            self.closed = True
            self.close_code = code
            self.close_reason = reason

    for _ in range(10):
        socket = FakeSocket(token)
        result = await authenticate_websocket(socket)
        assert result is not None

    socket = FakeSocket(token)
    result = await authenticate_websocket(socket)
    assert result is None
    assert socket.closed is True
    assert socket.close_code == 4429
    assert socket.sent[-1] == {"event": "auth_error", "payload": {"reason": "rate_limited"}}
