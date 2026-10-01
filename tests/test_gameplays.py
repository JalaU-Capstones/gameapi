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

    response = await client.post("/api/v1/gameplays", json=payload, headers=auth_headers)
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
        "/api/v1/gameplays",
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
        "/api/v1/gameplays",
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
        "/api/v1/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user["id"],
            "guestPlayer": "00000000-0000-0000-0000-000000000000",
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
        "/api/v1/users",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    other_id = other.json()["id"]

    response = await client.post(
        "/api/v1/gameplays",
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

    response = await client.get("/api/v1/gameplays/my-gameplays", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_my_gameplays_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/gameplays/my-gameplays")
    assert response.status_code == 401


async def test_list_gameplays(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    await _create_gameplay(client, auth_headers, registered_user["id"])
    await _create_gameplay(client, auth_headers, registered_user["id"])

    response = await client.get("/api/v1/gameplays", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_gameplays_by_player(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    await _create_gameplay(client, auth_headers, registered_user["id"])

    response = await client.get(
        f"/api/v1/gameplays/player/{registered_user['id']}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_list_gameplays_by_player_with_invalid_uuid_returns_empty(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v1/gameplays/player/not-a-uuid", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_get_gameplay_by_id(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])

    response = await client.get(f"/api/v1/gameplays/{gameplay['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == gameplay["id"]


async def test_get_gameplay_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/gameplays/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_v2_get_gameplay_by_stranger_returns_403(
    client: AsyncClient,
    registered_user_a: dict,
    registered_user_b: dict,
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    payload = {
        "currentPositions": VALID_BOARD,
        "hostPlayer": registered_user_a["id"],
        "guestPlayer": registered_user_b["id"],
        "playerTurn": registered_user_a["id"],
    }
    create_response = await client.post(
        "/api/v1/gameplays",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token_a}"},
    )
    assert create_response.status_code == 201, create_response.text
    gameplay_id = create_response.json()["id"]

    stranger = await client.post(
        "/api/v1/users",
        json={"name": "Stranger", "email": "stranger@example.com", "password": "password123"},
    )
    assert stranger.status_code == 201
    stranger_login = await client.post(
        "/api/v1/users/login",
        json={"email": "stranger@example.com", "password": "password123"},
    )
    stranger_headers = {"Authorization": f"Bearer {stranger_login.json()['token']}"}

    response = await client.get(f"/api/v2/gameplays/{gameplay_id}", headers=stranger_headers)
    assert response.status_code == 403, response.text


async def test_v2_get_gameplay_by_participant_returns_200(
    client: AsyncClient,
    registered_user_a: dict,
    registered_user_b: dict,
    auth_token_a: str,
) -> None:
    gameplay = await client.post(
        "/api/v1/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user_a["id"],
            "guestPlayer": registered_user_b["id"],
            "playerTurn": registered_user_a["id"],
        },
        headers={"Authorization": f"Bearer {auth_token_a}"},
    )
    assert gameplay.status_code == 201, gameplay.text

    response = await client.get(
        f"/api/v2/gameplays/{gameplay.json()['id']}",
        headers={"Authorization": f"Bearer {auth_token_a}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["id"] == gameplay.json()["id"]


async def test_v2_my_gameplays_only_returns_own(
    client: AsyncClient,
    registered_user_a: dict,
    registered_user_b: dict,
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    first = await client.post(
        "/api/v1/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user_a["id"],
            "playerTurn": registered_user_a["id"],
        },
        headers={"Authorization": f"Bearer {auth_token_a}"},
    )
    second = await client.post(
        "/api/v1/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user_b["id"],
            "guestPlayer": registered_user_a["id"],
            "playerTurn": registered_user_b["id"],
        },
        headers={"Authorization": f"Bearer {auth_token_b}"},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    response = await client.get(
        "/api/v2/gameplays/my-gameplays",
        headers={"Authorization": f"Bearer {auth_token_a}"},
    )
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert first.json()["id"] in ids
    assert second.json()["id"] in ids
    assert len(ids) == 2


async def test_v2_gameplay_access_rejects_non_participants_and_missing_records(
    client: AsyncClient,
    registered_user_a: dict,
    registered_user_b: dict,
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    gameplay = await client.post(
        "/api/v1/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user_a["id"],
            "playerTurn": registered_user_a["id"],
        },
        headers={"Authorization": f"Bearer {auth_token_a}"},
    )
    assert gameplay.status_code == 201

    stranger = await client.get(
        f"/api/v2/gameplays/{gameplay.json()['id']}",
        headers={"Authorization": f"Bearer {auth_token_b}"},
    )
    assert stranger.status_code == 403

    missing = await client.get(
        "/api/v2/gameplays/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {auth_token_a}"},
    )
    assert missing.status_code == 404


async def test_update_gameplay(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])

    updated_board = '{"board": [[1,0,0],[0,0,0],[0,0,0]], "lastMove": {"x":0,"y":0}}'
    response = await client.put(
        f"/api/v1/gameplays/{gameplay['id']}",
        json={"currentPositions": updated_board, "matchResult": None},
        headers=auth_headers,
    )
    assert response.status_code == 204

    fetched = await client.get(f"/api/v1/gameplays/{gameplay['id']}", headers=auth_headers)
    assert fetched.json()["currentPositions"] == updated_board


async def test_update_gameplay_with_match_result(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])

    response = await client.put(
        f"/api/v1/gameplays/{gameplay['id']}",
        json={"matchResult": '{"winner":"X"}'},
        headers=auth_headers,
    )
    assert response.status_code == 204

    fetched = await client.get(f"/api/v1/gameplays/{gameplay['id']}", headers=auth_headers)
    assert fetched.json()["matchResult"] == '{"winner": "X"}'


async def test_update_gameplay_with_new_guest_player(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])
    guest = await client.post(
        "/api/v1/users",
        json={"name": "Guest", "email": "guest@example.com", "password": "password123"},
    )
    assert guest.status_code == 201

    response = await client.put(
        f"/api/v1/gameplays/{gameplay['id']}",
        json={"guestPlayer": guest.json()["id"]},
        headers=auth_headers,
    )
    assert response.status_code == 204

    fetched = await client.get(f"/api/v1/gameplays/{gameplay['id']}", headers=auth_headers)
    assert fetched.json()["guestPlayer"] == guest.json()["id"]


async def test_update_gameplay_with_new_host_player(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])
    other = await client.post(
        "/api/v1/users",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    assert other.status_code == 201

    class StubPayload:
        def __init__(self) -> None:
            self.model_fields_set = {"host_player"}
            self.host_player = other.json()["id"]

    service = __import__("gameapi.services", fromlist=["GameplayService"]).GameplayService(
        db_session
    )

    await service.update(gameplay["id"], StubPayload())

    updated = await service.get_by_id(gameplay["id"])
    assert updated is not None
    assert updated.host_player == other.json()["id"]


async def test_update_gameplay_with_new_player_turn(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])
    other = await client.post(
        "/api/v1/users",
        json={"name": "Turn User", "email": "turn@example.com", "password": "password123"},
    )
    assert other.status_code == 201

    response = await client.put(
        f"/api/v1/gameplays/{gameplay['id']}",
        json={"playerTurn": other.json()["id"]},
        headers=auth_headers,
    )
    assert response.status_code == 204

    fetched = await client.get(f"/api/v1/gameplays/{gameplay['id']}", headers=auth_headers)
    assert fetched.json()["playerTurn"] == other.json()["id"]


async def test_update_gameplay_with_invalid_uuid_returns_404(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    response = await client.put(
        "/api/v1/gameplays/not-a-uuid",
        json={"matchResult": '{"winner":"X"}'},
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_update_gameplay_with_valid_nonexistent_uuid_returns_404(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    response = await client.put(
        "/api/v1/gameplays/00000000-0000-0000-0000-000000000000",
        json={"matchResult": '{"winner":"X"}'},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Gameplay not found"


async def test_delete_gameplay_with_invalid_uuid_returns_404(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    response = await client.delete("/api/v1/gameplays/not-a-uuid", headers=auth_headers)
    assert response.status_code == 404


async def test_delete_gameplay_with_valid_nonexistent_uuid_returns_404(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    response = await client.delete(
        "/api/v1/gameplays/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Gameplay not found"


async def test_update_gameplay_by_stranger_returns_403(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await _create_gameplay(client, auth_headers, registered_user["id"])

    other = await client.post(
        "/api/v1/users",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    other_login = await client.post(
        "/api/v1/users/login",
        json={"email": "other@example.com", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['token']}"}

    response = await client.put(
        f"/api/v1/gameplays/{gameplay['id']}",
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

    response = await client.delete(f"/api/v1/gameplays/{gameplay['id']}", headers=auth_headers)
    assert response.status_code == 204

    fetched = await client.get(f"/api/v1/gameplays/{gameplay['id']}", headers=auth_headers)
    assert fetched.status_code == 404
