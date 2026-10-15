import json

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
