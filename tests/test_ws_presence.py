from __future__ import annotations

from collections.abc import Callable

import pytest
from anyio import EndOfStream
from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws


def _contains_end_of_stream(exc: BaseException) -> bool:
    if isinstance(exc, EndOfStream):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_end_of_stream(sub) for sub in exc.exceptions)
    return False


async def test_ws_presence_valid_auth(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/presence",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        msg = await ws.receive_json()
        assert msg == {
            "event": "auth_ok",
            "payload": {"user_id": str(registered_user["id"])},
        }


async def test_ws_presence_list_online_users(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/presence",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()

        await ws.send_json({"event": "list_online_users"})
        assert await ws.receive_json() == {
            "event": "online_users",
            "payload": {"users": [str(registered_user["id"])]},
        }


async def test_ws_presence_notifies_other_connections(
    ws_client_factory: Callable[[], AsyncClient],
    client: AsyncClient,
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    other_payload = {
        "name": "Presence User B",
        "email": "presence-b@example.com",
        "password": "password123",
    }
    response = await client.post("/api/v1/users", json=other_payload)
    assert response.status_code == 201, response.text
    other_token = str(
        (
            await client.post(
                "/api/v1/users/login",
                json={"email": other_payload["email"], "password": other_payload["password"]},
            )
        ).json()["token"]
    )

    async with (
        ws_client_factory() as client_a,
        aconnect_ws(
            "ws://test/api/v2/ws/presence",
            client=client_a,
        ) as ws_a,
    ):
        await ws_a.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws_a.receive_json()

        async with (
            ws_client_factory() as client_b,
            aconnect_ws(
                "ws://test/api/v2/ws/presence",
                client=client_b,
            ) as ws_b,
        ):
            await ws_b.send_json({"event": "auth", "payload": {"token": other_token}})
            await ws_b.receive_json()
            msg = await ws_a.receive_json()
            assert msg == {
                "event": "user_online",
                "payload": {"user_id": str(response.json()["id"])},
            }


async def test_ws_presence_user_offline_notification(
    ws_client_factory: Callable[[], AsyncClient],
    client: AsyncClient,
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    other_payload = {
        "name": "Presence User B",
        "email": "presence-b@example.com",
        "password": "password123",
    }
    response = await client.post("/api/v1/users", json=other_payload)
    other_token = str(
        (
            await client.post(
                "/api/v1/users/login",
                json={"email": other_payload["email"], "password": other_payload["password"]},
            )
        ).json()["token"]
    )

    try:
        async with (
            ws_client_factory() as client_a,
            aconnect_ws(
                "ws://test/api/v2/ws/presence",
                client=client_a,
            ) as ws_a,
        ):
            await ws_a.send_json({"event": "auth", "payload": {"token": auth_token}})
            await ws_a.receive_json()

            async with (
                ws_client_factory() as client_b,
                aconnect_ws(
                    "ws://test/api/v2/ws/presence",
                    client=client_b,
                ) as ws_b,
            ):
                await ws_b.send_json({"event": "auth", "payload": {"token": other_token}})
                await ws_b.receive_json()
                await ws_a.receive_json()
                await ws_b.close()
                assert await ws_a.receive_json() == {
                    "event": "user_offline",
                    "payload": {"user_id": str(response.json()["id"])},
                }
    except BaseExceptionGroup as exc:
        if not _contains_end_of_stream(exc):
            raise


async def test_ws_presence_invalid_token_closes_connection(
    ws_client_factory: Callable[[], AsyncClient],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/presence",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": "invalid"}})
        assert await ws.receive_json() == {
            "event": "auth_error",
            "payload": {"reason": "invalid_token"},
        }
        with pytest.raises(WebSocketDisconnect) as exc:
            await ws.receive_json()
        assert exc.value.code == 4401
