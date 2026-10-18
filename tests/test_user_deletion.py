import json
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from gameapi.core.config import settings
from gameapi.db.models.refresh_token import RefreshToken
from gameapi.db.models.session import Session
from gameapi.main import app, global_exception_handler
from gameapi.services.exceptions import UserNotFoundError
from gameapi.services.user_service import UserService

VALID_BOARD = '{"board": [[0,0,0],[0,0,0],[0,0,0]], "lastMove": null}'


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _finished_game(client: AsyncClient, host: dict, guest: dict, host_token: str) -> dict:
    response = await client.post(
        "/api/v1/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": host["id"],
            "guestPlayer": guest["id"],
            "playerTurn": guest["id"],
            "matchResult": json.dumps({"winner": host["id"], "reason": "win"}),
        },
        headers=_bearer(host_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_guest_holding_the_turn_can_delete_account_and_rival_keeps_history(
    client: AsyncClient,
    registered_user_a: dict,
    registered_user_b: dict,
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    game = await _finished_game(client, registered_user_a, registered_user_b, auth_token_a)

    deleted = await client.delete(
        f"/api/v2/users/{registered_user_b['id']}", headers=_bearer(auth_token_b)
    )
    assert deleted.status_code == 204, deleted.text

    history = await client.get("/api/v2/gameplays/my-gameplays", headers=_bearer(auth_token_a))
    assert history.status_code == 200, history.text
    [item] = history.json()
    assert item["id"] == game["id"]
    assert item["hostPlayer"] == registered_user_a["id"]
    assert item["guestPlayer"] is None
    assert item["playerTurn"] is None


async def test_host_can_delete_account_and_guest_keeps_the_game(
    client: AsyncClient,
    registered_user_a: dict,
    registered_user_b: dict,
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    game = await _finished_game(client, registered_user_a, registered_user_b, auth_token_a)

    deleted = await client.delete(
        f"/api/v2/users/{registered_user_a['id']}", headers=_bearer(auth_token_a)
    )
    assert deleted.status_code == 204, deleted.text

    response = await client.get(f"/api/v2/gameplays/{game['id']}", headers=_bearer(auth_token_b))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["hostPlayer"] is None
    assert body["guestPlayer"] == registered_user_b["id"]


@pytest.mark.parametrize(
    ("invitation_state", "deleter"),
    [("accepted", "guest"), ("pending", "guest"), ("queued", "guest"), ("pending", "host")],
)
async def test_cannot_delete_account_with_an_open_game_or_invitation(
    client: AsyncClient,
    registered_user_a: dict,
    registered_user_b: dict,
    auth_token_a: str,
    auth_token_b: str,
    invitation_state: str,
    deleter: str,
) -> None:
    created = await client.post(
        "/api/v1/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user_a["id"],
            "guestPlayer": registered_user_b["id"],
            "playerTurn": registered_user_a["id"],
            "invitationState": invitation_state,
        },
        headers=_bearer(auth_token_a),
    )
    assert created.status_code == 201, created.text

    user, token = (
        (registered_user_b, auth_token_b)
        if deleter == "guest"
        else (registered_user_a, auth_token_a)
    )
    deleted = await client.delete(f"/api/v2/users/{user['id']}", headers=_bearer(token))
    assert deleted.status_code == 409, deleted.text

    still_there = await client.get(f"/api/v2/users/{user['id']}", headers=_bearer(token))
    assert still_there.status_code == 200, still_there.text


async def test_v1_delete_also_refuses_with_an_active_game(
    client: AsyncClient,
    registered_user_a: dict,
    registered_user_b: dict,
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    created = await client.post(
        "/api/v1/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user_a["id"],
            "guestPlayer": registered_user_b["id"],
            "playerTurn": registered_user_a["id"],
        },
        headers=_bearer(auth_token_a),
    )
    assert created.status_code == 201, created.text

    deleted = await client.delete(
        f"/api/v1/users/{registered_user_b['id']}", headers=_bearer(auth_token_b)
    )
    assert deleted.status_code == 409, deleted.text


async def test_delete_user_cascades_sessions_and_tokens(
    client: AsyncClient,
    db_session,
    registered_user_a: dict,
) -> None:
    login = await client.post(
        "/api/v2/auth/login",
        json={
            "email": registered_user_a["email"],
            "password": "password123",
        },
    )
    assert login.status_code == 200, login.text
    user_id = UUID(str(registered_user_a["id"]))

    sessions_before_delete = (
        (await db_session.execute(select(Session).where(Session.user_id == user_id)))
        .scalars()
        .all()
    )
    tokens_before_delete = (
        (await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id)))
        .scalars()
        .all()
    )
    assert sessions_before_delete
    assert tokens_before_delete

    deleted = await client.delete(
        f"/api/v2/users/{user_id}",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert deleted.status_code == 204, deleted.text

    sessions_after_delete = (
        (await db_session.execute(select(Session).where(Session.user_id == user_id)))
        .scalars()
        .all()
    )
    tokens_after_delete = (
        (await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id)))
        .scalars()
        .all()
    )
    assert sessions_after_delete == []
    assert tokens_after_delete == []


@pytest.mark.parametrize("user_id", ["not-a-uuid", str(UUID(int=0))])
async def test_delete_unknown_user_raises_not_found(db_session, user_id: str) -> None:
    with pytest.raises(UserNotFoundError):
        await UserService(db_session).delete(user_id)


async def test_unhandled_exception_response_includes_cors_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.app, "cors_origins", ["https://allowed.example"])

    async def fail() -> None:
        raise RuntimeError("Unexpected failure")

    path = "/__test/unhandled-exception"
    assert not any(getattr(route, "path", None) == path for route in app.router.routes)
    app.add_api_route(path, fail, methods=["GET"])
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as test_client:
            for origin, expected_origin in (
                ("https://allowed.example", "https://allowed.example"),
                ("https://unallowed.example", None),
                (None, None),
            ):
                headers = {"Origin": origin} if origin is not None else {}
                response = await test_client.get(path, headers=headers)

                assert response.status_code == 500
                assert response.json() == {"detail": "Internal server error"}
                assert response.headers.get("access-control-allow-origin") == expected_origin
                if expected_origin is not None:
                    assert response.headers["access-control-allow-credentials"] == "true"
                    assert response.headers["vary"] == "Origin"
                assert app.exception_handlers[Exception] is global_exception_handler
    finally:
        app.router.routes[:] = [
            route for route in app.router.routes if getattr(route, "path", None) != path
        ]
