from httpx import AsyncClient

VALID_BOARD = '{"board": [[0,0,0],[0,0,0],[0,0,0]], "lastMove": null}'


async def _create_gameplay(
    client: AsyncClient,
    auth_headers: dict[str, str],
    host_id: str,
    guest_id: str | None = None,
) -> dict:
    payload: dict[str, object] = {
        "currentPositions": VALID_BOARD,
        "hostPlayer": host_id,
        "playerTurn": host_id,
        "matchResult": None,
    }
    if guest_id is not None:
        payload["guestPlayer"] = guest_id

    response = await client.post("/api/gameplays", json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_gameplay(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])
    assert gameplay["hostPlayer"] == registered_user["id"]
    assert gameplay["currentPositions"] == VALID_BOARD
    assert gameplay["guestPlayer"] is None
    assert gameplay["matchResult"] is None


async def test_create_gameplay_without_token_returns_401(
    client: AsyncClient,
    registered_user: dict,
) -> None:
    response = await client.post(
        "/api/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user["id"],
            "playerTurn": registered_user["id"],
        },
    )
    assert response.status_code == 401


async def test_create_gameplay_with_invalid_json_positions_returns_400(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/gameplays",
        json={
            "currentPositions": "{not valid json}",
            "hostPlayer": registered_user["id"],
            "playerTurn": registered_user["id"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "message" in response.json()


async def test_create_gameplay_with_nonexistent_guest_returns_400(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user["id"],
            "guestPlayer": "000000000000000000000000",
            "playerTurn": registered_user["id"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["message"] == "Guest player does not exist"


async def test_create_gameplay_as_another_host_returns_403(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    other = await client.post(
        "/api/users",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    other_id = other.json()["id"]

    response = await client.post(
        "/api/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": other_id,
            "playerTurn": other_id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 403


async def test_list_my_gameplays(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    await _create_gameplay(client, auth_headers, registered_user["id"])
    await _create_gameplay(client, auth_headers, registered_user["id"])

    response = await client.get("/api/gameplays/my-gameplays", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_my_gameplays_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/gameplays/my-gameplays")
    assert response.status_code == 401


async def test_list_gameplays_by_player(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    await _create_gameplay(client, auth_headers, registered_user["id"])

    response = await client.get(f"/api/gameplays/player/{registered_user['id']}")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_get_gameplay_by_id(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])

    response = await client.get(f"/api/gameplays/{gameplay['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == gameplay["id"]


async def test_get_gameplay_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/gameplays/000000000000000000000000")
    assert response.status_code == 404


async def test_update_gameplay(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])

    updated_board = '{"board": [[1,0,0],[0,0,0],[0,0,0]], "lastMove": {"x":0,"y":0}}'
    response = await client.put(
        f"/api/gameplays/{gameplay['id']}",
        json={"currentPositions": updated_board, "matchResult": None},
        headers=auth_headers,
    )
    assert response.status_code == 204

    fetched = await client.get(f"/api/gameplays/{gameplay['id']}")
    assert fetched.json()["currentPositions"] == updated_board


async def test_update_gameplay_by_stranger_returns_403(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])

    other = await client.post(
        "/api/users",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    other_login = await client.post(
        "/api/users/login",
        json={"email": "other@example.com", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['token']}"}

    response = await client.put(
        f"/api/gameplays/{gameplay['id']}",
        json={"currentPositions": VALID_BOARD},
        headers=other_headers,
    )
    assert response.status_code == 403
    assert other.json()["id"] != registered_user["id"]


async def test_delete_gameplay_by_host(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])

    response = await client.delete(f"/api/gameplays/{gameplay['id']}", headers=auth_headers)
    assert response.status_code == 204

    fetched = await client.get(f"/api/gameplays/{gameplay['id']}")
    assert fetched.status_code == 404
