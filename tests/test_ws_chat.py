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


async def _read_event(ws, event_name: str):
    while True:
        message = await ws.receive_json()
        if message["event"] == event_name:
            return message


async def test_ws_chat_auth_and_history(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws("ws://test/api/v2/ws/chat", client=client) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        assert await ws.receive_json() == {
            "event": "auth_ok",
            "payload": {"user_id": str(registered_user["id"])},
        }
        msg = await ws.receive_json()
        assert msg["event"] == "chat_history"
        assert msg["payload"]["users_count"] == 1
        assert isinstance(msg["payload"]["messages"], list)


async def test_ws_chat_count_notifications_on_join_and_leave(
    ws_client_factory: Callable[[], AsyncClient],
    client: AsyncClient,
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    other_payload = {
        "name": "Chat User B",
        "email": "chat-b@example.com",
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
        aconnect_ws("ws://test/api/v2/ws/chat", client=client_a) as ws_a,
    ):
        await ws_a.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws_a.receive_json()
        await ws_a.receive_json()

        try:
            async with (
                ws_client_factory() as client_b,
                aconnect_ws("ws://test/api/v2/ws/chat", client=client_b) as ws_b,
            ):
                await ws_b.send_json({"event": "auth", "payload": {"token": other_token}})
                await ws_b.receive_json()
                await ws_b.receive_json()
                assert await _read_event(ws_a, "chat_users_count") == {
                    "event": "chat_users_count",
                    "payload": {"count": 2},
                }

                await ws_b.close()
                assert await _read_event(ws_a, "chat_users_count") == {
                    "event": "chat_users_count",
                    "payload": {"count": 1},
                }
        except BaseExceptionGroup as exc:
            assert _contains_end_of_stream(exc)


async def test_ws_chat_rejects_duplicate_session(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
) -> None:
    async with (
        ws_client_factory() as client_a,
        aconnect_ws("ws://test/api/v2/ws/chat", client=client_a) as ws_a,
    ):
        await ws_a.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws_a.receive_json()
        await ws_a.receive_json()

        async with (
            ws_client_factory() as client_b,
            aconnect_ws("ws://test/api/v2/ws/chat", client=client_b) as ws_b,
        ):
            await ws_b.send_json({"event": "auth", "payload": {"token": auth_token}})
            with pytest.raises(WebSocketDisconnect) as exc:
                await ws_b.receive_json()
            assert exc.value.code == 4409

        await ws_a.send_json({"event": "ping"})
        assert await ws_a.receive_json() == {"event": "pong", "payload": {}}


async def test_ws_chat_send_broadcasts_message_and_sanitization(
    ws_client_factory: Callable[[], AsyncClient],
    client: AsyncClient,
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    other_payload = {
        "name": "Chat User B",
        "email": "chat-b2@example.com",
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
        aconnect_ws("ws://test/api/v2/ws/chat", client=client_a) as ws_a,
    ):
        await ws_a.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws_a.receive_json()
        await ws_a.receive_json()

        async with (
            ws_client_factory() as client_b,
            aconnect_ws("ws://test/api/v2/ws/chat", client=client_b) as ws_b,
        ):
            await ws_b.send_json({"event": "auth", "payload": {"token": other_token}})
            await ws_b.receive_json()
            await ws_b.receive_json()
            await _read_event(ws_a, "chat_users_count")

            await ws_a.send_json(
                {"event": "chat_send", "payload": {"content": "\u202ehello\u200b"}}
            )
            msg_a = await _read_event(ws_a, "chat_message")
            msg_b = await _read_event(ws_b, "chat_message")
            assert msg_a["payload"]["content"] == "hello"
            assert msg_b["payload"]["content"] == "hello"
            assert msg_a["payload"]["id"] == msg_b["payload"]["id"]
            assert msg_a["payload"]["user_name"] == str(registered_user["name"])


async def test_ws_chat_empty_and_too_long_and_raw_cap(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws("ws://test/api/v2/ws/chat", client=client) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()
        await ws.receive_json()

        await ws.send_json({"event": "chat_send", "payload": {"content": "   \u200b  "}})
        assert await ws.receive_json() == {
            "event": "chat_error",
            "payload": {
                "code": "CHAT_MESSAGE_EMPTY",
                "message": "Chat message is empty after sanitization",
            },
        }

        await ws.send_json({"event": "chat_send", "payload": {"content": "a" * 501}})
        assert await ws.receive_json() == {
            "event": "chat_error",
            "payload": {
                "code": "CHAT_MESSAGE_TOO_LONG",
                "message": "Chat message exceeds the maximum allowed length",
            },
        }

        await ws.send_json({"event": "chat_send", "payload": {"content": "a" * 2500}})
        assert await ws.receive_json() == {
            "event": "chat_error",
            "payload": {
                "code": "CHAT_MESSAGE_TOO_LONG",
                "message": "Content exceeds the maximum allowed length",
            },
        }


async def test_ws_chat_rate_limit_and_unknown_event_and_invalid_payload(
    ws_client_factory: Callable[[], AsyncClient],
    client: AsyncClient,
    auth_token: str,
    registered_user: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    monkeypatch.setattr("gameapi.services.chat_service.chat_service._monotonic_fn", lambda: now[0])

    other_payload = {
        "name": "Chat User B",
        "email": "chat-b3@example.com",
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
        aconnect_ws("ws://test/api/v2/ws/chat", client=client_a) as ws_a,
    ):
        await ws_a.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws_a.receive_json()
        await ws_a.receive_json()

        async with (
            ws_client_factory() as client_b,
            aconnect_ws("ws://test/api/v2/ws/chat", client=client_b) as ws_b,
        ):
            await ws_b.send_json({"event": "auth", "payload": {"token": other_token}})
            await ws_b.receive_json()
            await ws_b.receive_json()
            await ws_a.receive_json()  # join count notification

            for _ in range(10):
                await ws_a.send_json({"event": "chat_send", "payload": {"content": "hello"}})
                assert (await _read_event(ws_a, "chat_message"))["event"] == "chat_message"

            await ws_a.send_json({"event": "chat_send", "payload": {"content": "hello"}})
            assert await _read_event(ws_a, "chat_error") == {
                "event": "chat_error",
                "payload": {
                    "code": "CHAT_RATE_LIMITED",
                    "message": "Chat rate limit exceeded; retry after some time",
                    "retry_after_seconds": 30,
                },
            }

            await ws_b.send_json({"event": "chat_send", "payload": {"content": "still okay"}})
            assert (await _read_event(ws_b, "chat_message"))["event"] == "chat_message"
            assert (await _read_event(ws_a, "chat_message"))["event"] == "chat_message"

            await ws_a.send_json({"event": "foo"})
            assert await _read_event(ws_a, "chat_error") == {
                "event": "chat_error",
                "payload": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "Event not implemented yet: foo",
                },
            }

            await ws_a.send_json({"event": "chat_send", "payload": "not-an-object"})
            assert await _read_event(ws_a, "chat_error") == {
                "event": "chat_error",
                "payload": {"code": "INVALID_PAYLOAD", "message": "Missing 'payload'"},
            }

            await ws_a.send_json({"event": "chat_send", "payload": {}})
            assert await _read_event(ws_a, "chat_error") == {
                "event": "chat_error",
                "payload": {"code": "INVALID_PAYLOAD", "message": "Invalid payload"},
            }

            await ws_a.send_json({"event": "ping"})
            assert await ws_a.receive_json() == {"event": "pong", "payload": {}}


async def test_ws_chat_unknown_user_fallback(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_by_id(self, user_id: str):
        return None

    monkeypatch.setattr("gameapi.services.user_service.UserService.get_by_id", _fake_get_by_id)

    async with (
        ws_client_factory() as client,
        aconnect_ws("ws://test/api/v2/ws/chat", client=client) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        assert await ws.receive_json() == {
            "event": "auth_ok",
            "payload": {"user_id": str(registered_user["id"])},
        }
        await ws.receive_json()

        await ws.send_json({"event": "chat_send", "payload": {"content": "hello"}})
        message = await ws.receive_json()
        assert message["event"] == "chat_message"
        assert message["payload"]["user_name"] == "Unknown"
