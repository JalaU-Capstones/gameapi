from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.api.v2.ws.auth import authenticate_websocket
from gameapi.api.v2.ws.manager import gameplays_manager
from gameapi.core.idempotency import lookup_ws_create_game, remember_ws_create_game
from gameapi.db.session import PostgresDatabase
from gameapi.schemas.ws_events import (
    AcceptInvitationPayload,
    CreateGamePayload,
    LeaveGamePayload,
    PlayMovePayload,
    RejectInvitationPayload,
)
from gameapi.services.event_bus import event_bus
from gameapi.services.exceptions import (
    CannotInviteSelfError,
    DomainError,
    GameNotActiveError,
    GameplayNotFoundError,
    HostBusyError,
    InvalidMoveError,
    InvitationNotPendingError,
    NotAParticipantError,
    NotYourTurnError,
    OpponentOfflineError,
    UserBusyError,
)
from gameapi.services.game_engine_service import GameEngineService
from gameapi.services.gameplay_service import GameplayService
from gameapi.services.player_status import is_playing, set_players_status
from gameapi.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter()


def _map_domain_error(exc: DomainError) -> str:
    if isinstance(exc, NotYourTurnError):
        return "NOT_YOUR_TURN"
    if isinstance(exc, InvalidMoveError):
        return "INVALID_MOVE"
    if isinstance(exc, GameplayNotFoundError):
        return "GAME_NOT_FOUND"
    if isinstance(exc, GameNotActiveError):
        return "GAME_NOT_ACTIVE"
    if isinstance(exc, NotAParticipantError):
        return "NOT_A_PARTICIPANT"
    if isinstance(exc, InvitationNotPendingError):
        return "INVITATION_NOT_PENDING"
    if isinstance(exc, CannotInviteSelfError):
        return "CANNOT_INVITE_SELF"
    if isinstance(exc, OpponentOfflineError):
        return "OPPONENT_OFFLINE"
    if isinstance(exc, HostBusyError):
        return "HOST_BUSY"
    if isinstance(exc, UserBusyError):
        return "USER_BUSY"
    return "UNKNOWN_ERROR"


async def _handle_message(
    user_id: str,
    message: dict[str, Any],
    websocket: WebSocket,
    current_game_id: str | None,
    engine_service: GameEngineService,
    session: AsyncSession,
) -> str | None:
    event = message.get("event") if isinstance(message, dict) else None
    if event is None:
        await websocket.send_json(
            {
                "event": "error",
                "payload": {"code": "INVALID_EVENT", "message": "Missing 'event' field"},
            }
        )
        return current_game_id

    if event == "ping":
        await websocket.send_json({"event": "pong", "payload": {}})
        return current_game_id

    if event == "ws_connected":
        logger.info(
            "WebSocket connected",
            extra={"event_type": "ws_connected", "player_id": user_id},
        )
        return current_game_id

    if event == "unknown":
        await websocket.send_json(
            {
                "event": "error",
                "payload": {
                    "code": "NOT_IMPLEMENTED",
                    "message": f"Event not implemented yet: {event}",
                },
            }
        )
        return current_game_id

    payload_raw = message.get("payload") if isinstance(message, dict) else {}
    if not isinstance(payload_raw, dict):
        await websocket.send_json(
            {
                "event": "error",
                "payload": {"code": "INVALID_PAYLOAD", "message": "Missing 'payload'"},
            }
        )
        return current_game_id

    async def _ws_callback(event_dict: dict[str, Any]) -> None:
        try:
            await websocket.send_json(event_dict)
        except (WebSocketDisconnect, RuntimeError):
            logger.info(
                "WebSocket disconnected while sending gameplay event for user '%s'", user_id
            )

    try:
        if event == "subscribe_game":
            payload_sub = payload_raw if isinstance(payload_raw, dict) else {}
            game_id = payload_sub.get("game_id")
            if not isinstance(game_id, str) or not game_id:
                await websocket.send_json(
                    {
                        "event": "error",
                        "payload": {
                            "code": "INVALID_PAYLOAD",
                            "message": "Missing 'game_id' field",
                        },
                    }
                )
                return current_game_id

            if current_game_id is not None and current_game_id != game_id:
                event_bus.unsubscribe(current_game_id, user_id)

            event_bus.subscribe(game_id, user_id, _ws_callback)
            logger.info(
                "Game created",
                extra={
                    "event_type": "game_created",
                    "player_id": user_id,
                    "metadata": {
                        "game_id": game_id,
                        "host_id": user_id,
                        "guest_id": payload_sub.get("guest_id"),
                    },
                },
            )
            await websocket.send_json({"event": "subscribed", "payload": {"game_id": game_id}})
            return game_id

        if event == "unsubscribe_game":
            payload_sub = payload_raw if isinstance(payload_raw, dict) else {}
            game_id = payload_sub.get("game_id")
            if not isinstance(game_id, str) or not game_id:
                await websocket.send_json(
                    {
                        "event": "error",
                        "payload": {
                            "code": "INVALID_PAYLOAD",
                            "message": "Missing 'game_id' field",
                        },
                    }
                )
                return current_game_id

            event_bus.unsubscribe(game_id, user_id)
            await websocket.send_json({"event": "unsubscribed", "payload": {"game_id": game_id}})
            if current_game_id == game_id:
                return None
            return current_game_id

        if event == "broadcast_to_game":
            payload_broadcast = payload_raw if isinstance(payload_raw, dict) else {}
            game_id = payload_broadcast.get("game_id")
            payload_message = payload_broadcast.get("message")
            if not isinstance(game_id, str) or not game_id or not isinstance(payload_message, str):
                await websocket.send_json(
                    {
                        "event": "error",
                        "payload": {
                            "code": "INVALID_PAYLOAD",
                            "message": "Missing 'game_id' field",
                        },
                    }
                )
                return current_game_id

            await event_bus.publish(
                game_id,
                {
                    "event": "game_message",
                    "payload": {"from": user_id, "message": payload_message},
                },
            )
            await websocket.send_json({"event": "broadcast_sent", "payload": {"game_id": game_id}})
            return current_game_id

        if event == "create_game":
            payload = CreateGamePayload(**payload_raw)
            if payload.guest_id == user_id:
                raise CannotInviteSelfError(user_id)
            if not gameplays_manager.is_online(payload.guest_id):
                raise OpponentOfflineError(payload.guest_id)

            guest_active_game = await engine_service.gameplay_service.find_active_game_for_user(
                payload.guest_id
            )
            if guest_active_game is not None:
                if not is_playing(payload.guest_id):
                    await set_players_status([payload.guest_id], playing=True)
                raise UserBusyError(payload.guest_id)

            host_active = await engine_service.gameplay_service.find_active_game_for_user(user_id)
            host_pending = await engine_service.gameplay_service.has_pending_or_queued_invitation(
                user_id
            )
            if host_active is not None or host_pending:
                raise HostBusyError(user_id)

            request_id = payload_raw.get("client_request_id") or payload_raw.get("request_id")
            if isinstance(request_id, str) and request_id:
                cached = lookup_ws_create_game(host_id=user_id, request_id=request_id)
                if cached is not None:
                    return cached

            game_id = await engine_service.create_game(host_id=user_id, guest_id=payload.guest_id)
            if isinstance(request_id, str) and request_id:
                remember_ws_create_game(host_id=user_id, request_id=request_id, game_id=game_id)
            await session.commit()

            if current_game_id is not None and current_game_id != game_id:
                event_bus.unsubscribe(current_game_id, user_id)

            event_bus.subscribe(game_id, user_id, _ws_callback)

            logger.info(
                "Game created",
                extra={
                    "event_type": "game_created",
                    "player_id": user_id,
                    "metadata": {
                        "game_id": game_id,
                        "host_id": user_id,
                        "guest_id": payload.guest_id,
                    },
                },
            )
            await websocket.send_json(
                {
                    "event": "game_created",
                    "payload": {
                        "game_id": game_id,
                        "guest_id": payload.guest_id,
                        "board": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
                        "turn": user_id,
                    },
                }
            )

            host = await engine_service.user_service.get_by_id(user_id)
            host_name = host.name if host else "Unknown"

            await gameplays_manager.send_to(
                payload.guest_id,
                {
                    "event": "invitation_received",
                    "payload": {"game_id": game_id, "host": {"id": user_id, "name": host_name}},
                },
            )
            return game_id

        if event == "accept_invitation":
            payload_accept = AcceptInvitationPayload(**payload_raw)
            game_id = payload_accept.game_id

            await engine_service.accept_invitation(game_id=game_id, guest_id=user_id)
            await session.commit()

            if current_game_id is not None and current_game_id != game_id:
                event_bus.unsubscribe(current_game_id, user_id)

            event_bus.subscribe(game_id, user_id, _ws_callback)

            gameplay = await engine_service.gameplay_service.get_by_id(game_id)
            host_id = gameplay.host_player if gameplay else ""
            await set_players_status([host_id, user_id], playing=True)

            logger.info(
                "Invitation accepted",
                extra={
                    "event_type": "invitation_accepted",
                    "player_id": user_id,
                    "metadata": {"game_id": game_id},
                },
            )
            await event_bus.publish(
                game_id,
                {
                    "event": "invitation_accepted",
                    "payload": {
                        "game_id": game_id,
                        "board": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
                        "turn": host_id,
                    },
                },
            )
            return game_id

        if event == "reject_invitation":
            payload_reject = RejectInvitationPayload(**payload_raw)
            game_id = payload_reject.game_id

            await engine_service.reject_invitation(game_id=game_id, guest_id=user_id)
            await session.commit()

            gameplay = await engine_service.gameplay_service.get_by_id(game_id)
            host_id = gameplay.host_player if gameplay else None

            if host_id is not None:
                await gameplays_manager.send_to(
                    host_id,
                    {
                        "event": "invitation_rejected",
                        "payload": {"game_id": game_id, "guest_id": user_id},
                    },
                )
            return current_game_id

        if event == "play_move":
            payload_play = PlayMovePayload(**payload_raw)
            game_id = payload_play.game_id

            response_event = await engine_service.play_move(
                game_id=game_id, player_id=user_id, row=payload_play.row, col=payload_play.col
            )
            await session.commit()
            logger.info(
                "Move made",
                extra={
                    "event_type": "move_made",
                    "player_id": user_id,
                    "gameplay_id": game_id,
                    "metadata": {
                        "game_id": game_id,
                        "player_id": user_id,
                        "row": payload_play.row,
                        "col": payload_play.col,
                    },
                },
            )
            await event_bus.publish(game_id, response_event)
            if response_event.get("event") == "game_ended":
                gameplay = await engine_service.gameplay_service.get_by_id(game_id)
                if gameplay:
                    await set_players_status(
                        [gameplay.host_player, gameplay.guest_player], playing=False
                    )
            return current_game_id

        if event == "leave_game":
            payload_leave = LeaveGamePayload(**payload_raw)
            game_id = payload_leave.game_id

            transitioned = await engine_service.leave_game(game_id=game_id, player_id=user_id)
            await session.commit()
            if not transitioned:
                return current_game_id

            gameplay = await engine_service.gameplay_service.get_by_id(game_id)
            opponent_id = None
            board = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
            if gameplay:
                opponent_id = (
                    gameplay.guest_player
                    if user_id == gameplay.host_player
                    else gameplay.host_player
                )
                board = json.loads(gameplay.current_positions)["board"]
                await set_players_status([user_id, opponent_id], playing=False)

            logger.warning(
                "Game abandoned",
                extra={
                    "event_type": "game_abandoned",
                    "player_id": user_id,
                    "gameplay_id": game_id,
                    "metadata": {"game_id": game_id, "player_id": user_id},
                },
            )
            await event_bus.publish(
                game_id,
                {
                    "event": "game_ended",
                    "payload": {
                        "game_id": game_id,
                        "board": board,
                        "winner": opponent_id,
                        "reason": "abandon",
                        "winner_line": None,
                    },
                },
            )
            event_bus.unsubscribe(game_id, user_id)
            if current_game_id == game_id:
                return None
            return current_game_id

    except ValidationError as e:
        await websocket.send_json(
            {"event": "error", "payload": {"code": "INVALID_PAYLOAD", "message": str(e)}}
        )
    except DomainError as e:
        await websocket.send_json(
            {"event": "error", "payload": {"code": _map_domain_error(e), "message": str(e)}}
        )

    return current_game_id


ABANDON_GRACE_SECONDS = 20.0
_HANDOVER_REASONS = {"session_handover", "session_replaced"}
_pending_abandons: dict[str, asyncio.Task[None]] = {}


def reset_pending_abandons() -> None:
    """Cancel and clear every pending abandon task. TEST-ONLY."""
    for task in list(_pending_abandons.values()):
        task.cancel()
    _pending_abandons.clear()


async def _abandon_game(user_id: str, game_id: str) -> None:
    async with PostgresDatabase.session_factory()() as session:
        engine_service = GameEngineService(
            GameplayService(session), UserService(session), event_bus
        )
        try:
            transitioned = await engine_service.leave_game(game_id, player_id=user_id)
            await session.commit()
        except DomainError:
            await session.rollback()
            return

        if not transitioned:
            return

        gameplay = await engine_service.gameplay_service.get_by_id(game_id)
        if not gameplay:
            return

        opponent_id = (
            gameplay.guest_player if user_id == gameplay.host_player else gameplay.host_player
        )
        board = json.loads(gameplay.current_positions)["board"]
        await set_players_status([user_id, opponent_id], playing=False)
        logger.info(
            "Game ended",
            extra={
                "event_type": "game_ended",
                "player_id": user_id,
                "gameplay_id": game_id,
                "metadata": {"game_id": game_id, "winner": str(opponent_id), "reason": "abandon"},
            },
        )
        await event_bus.publish(
            game_id,
            {
                "event": "game_ended",
                "payload": {
                    "game_id": game_id,
                    "board": board,
                    "winner": opponent_id,
                    "reason": "abandon",
                    "winner_line": None,
                },
            },
        )


def _cancel_pending_abandon(user_id: str) -> None:
    task = _pending_abandons.pop(user_id, None)
    if task is not None:
        task.cancel()


def _schedule_abandon(user_id: str, game_id: str) -> None:
    """Give another tab of the same user time to take over the game before abandoning it."""
    _cancel_pending_abandon(user_id)

    async def _abandon_if_not_resumed() -> None:
        try:
            await asyncio.sleep(ABANDON_GRACE_SECONDS)
            if gameplays_manager.is_online(user_id) and event_bus.is_subscribed(game_id, user_id):
                return
            await _abandon_game(user_id, game_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Deferred abandon failed for game '%s'", game_id)
        finally:
            if _pending_abandons.get(user_id) is asyncio.current_task():
                _pending_abandons.pop(user_id, None)

    _pending_abandons[user_id] = asyncio.create_task(_abandon_if_not_resumed())


@router.websocket("/gameplays")
async def gameplays_websocket(websocket: WebSocket) -> None:
    user_id = await authenticate_websocket(websocket)
    if user_id is None:
        return

    if gameplays_manager.get_user_socket(user_id) is not None:
        await websocket.close(code=4409, reason="session_already_active")
        return

    await gameplays_manager.connect(user_id, websocket)
    _cancel_pending_abandon(user_id)
    await websocket.send_json({"event": "auth_ok", "payload": {"user_id": user_id}})

    current_game_id: str | None = None
    is_handover = False
    async with PostgresDatabase.session_factory()() as session:
        gameplay_service = GameplayService(session)
        user_service = UserService(session)
        engine_service = GameEngineService(gameplay_service, user_service, event_bus)

        try:
            while True:
                message = await websocket.receive_json()
                # Expire stale ORM cache so every read within this message fetches
                # fresh data from DB, including mutations made by other connections.
                session.expire_all()
                current_game_id = await _handle_message(
                    user_id, message, websocket, current_game_id, engine_service, session
                )
        except WebSocketDisconnect as exc:
            is_handover = exc.code == 4409 or exc.reason in _HANDOVER_REASONS
            logger.info(
                "WebSocket disconnected",
                extra={
                    "event_type": "ws_disconnected",
                    "player_id": user_id,
                    "metadata": {
                        "user_id": user_id,
                        "code": exc.code,
                        "reason": exc.reason or "disconnect",
                    },
                },
            )
        finally:
            with contextlib.suppress(Exception):
                await session.rollback()

    owns_subscription = gameplays_manager.get_user_socket(user_id) in (None, websocket)
    gameplays_manager.disconnect(user_id, websocket)
    if current_game_id is not None:
        if owns_subscription:
            event_bus.unsubscribe(current_game_id, user_id)
        if is_handover:
            _schedule_abandon(user_id, current_game_id)
        else:
            await _abandon_game(user_id, current_game_id)
