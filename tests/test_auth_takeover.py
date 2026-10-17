from unittest.mock import AsyncMock
from uuid import UUID

from httpx import AsyncClient

from gameapi.api.v2.ws.manager import gameplays_manager
from gameapi.core.security import decode_access_token
from gameapi.db.models.gameplay import Gameplay
from gameapi.repositories.session_repository import SessionRepository


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v2/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


async def test_takeover_requires_session_bound_token(
    client: AsyncClient,
    auth_token: str,
) -> None:
    response = await client.post(
        "/api/v2/auth/session/takeover",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SESSION_REQUIRED"


async def test_takeover_is_deferred_while_game_is_active(
    client: AsyncClient,
    db_session,
    registered_user: dict[str, object],
) -> None:
    token = await _login(client, str(registered_user["email"]))
    user_id = UUID(str(registered_user["id"]))
    db_session.add(Gameplay(host_player=user_id))
    await db_session.flush()

    response = await client.post(
        "/api/v2/auth/session/takeover",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "GAME_IN_PROGRESS"


async def test_takeover_revokes_other_sessions_and_is_idempotent(
    client: AsyncClient,
    db_session,
    registered_user: dict[str, object],
) -> None:
    user_id = str(registered_user["id"])
    old_token = await _login(client, str(registered_user["email"]))
    current_token = await _login(client, str(registered_user["email"]))
    old_sid = decode_access_token(old_token).sid
    current_sid = decode_access_token(current_token).sid
    assert old_sid is not None
    assert current_sid is not None

    old_socket = AsyncMock()
    current_socket = AsyncMock()
    await gameplays_manager.connect(user_id, old_socket, old_sid)
    await gameplays_manager.connect(user_id, current_socket, current_sid)

    headers = {"Authorization": f"Bearer {current_token}"}
    response = await client.post("/api/v2/auth/session/takeover", headers=headers)

    assert response.status_code == 204
    old_socket.close.assert_awaited_once_with(code=4409, reason="session_replaced")
    current_socket.close.assert_not_awaited()
    assert gameplays_manager.get_user_socket(user_id) is current_socket

    old_session = await SessionRepository(db_session).get_by_id(UUID(old_sid))
    current_session = await SessionRepository(db_session).get_by_id(UUID(current_sid))
    assert old_session is not None
    assert old_session.revoked_at is not None
    assert old_session.revoked_reason == "session_replaced"
    assert current_session is not None
    assert current_session.revoked_at is None

    repeated = await client.post("/api/v2/auth/session/takeover", headers=headers)
    assert repeated.status_code == 204
    current_socket.close.assert_not_awaited()
