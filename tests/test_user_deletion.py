import json

import pytest
from httpx import AsyncClient

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
