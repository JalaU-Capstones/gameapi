from unittest.mock import AsyncMock

from httpx import AsyncClient

from gameapi.api.v2.ws.auth import authenticate_websocket
from gameapi.core.security import decode_access_token


def _socket(token: str) -> AsyncMock:
    websocket = AsyncMock()
    websocket.receive_json.return_value = {
        "event": "auth",
        "payload": {"token": token},
    }
    return websocket


async def test_legacy_websocket_token_is_accepted_without_session_id(auth_token: str) -> None:
    websocket = _socket(auth_token)

    result = await authenticate_websocket(websocket)

    assert result is not None
    assert result[0] == decode_access_token(auth_token).sub
    assert result[1] is None
    websocket.close.assert_not_awaited()


async def test_session_replaced_websocket_token_is_rejected(
    client: AsyncClient,
    registered_user: dict[str, object],
) -> None:
    email = str(registered_user["email"])
    tokens: list[str] = []
    for _ in range(2):
        response = await client.post(
            "/api/v2/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert response.status_code == 200, response.text
        tokens.append(str(response.json()["access_token"]))

    old_token, current_token = tokens
    old_sid = decode_access_token(old_token).sid
    assert old_sid is not None

    takeover = await client.post(
        "/api/v2/auth/session/takeover",
        headers={"Authorization": f"Bearer {current_token}"},
    )
    assert takeover.status_code == 204, takeover.text

    websocket = _socket(old_token)
    assert await authenticate_websocket(websocket) is None
    websocket.send_json.assert_awaited_once_with(
        {
            "event": "auth_error",
            "payload": {"reason": "session_replaced"},
        }
    )
    websocket.close.assert_awaited_once_with(code=4409, reason="session_replaced")
