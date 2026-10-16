import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from gameapi.api.v2.ws.manager import gameplays_manager
from gameapi.schemas.gameplay import GameplayCreate, GameplayUpdate
from gameapi.services.event_bus import EventBus
from gameapi.services.exceptions import (
    CannotInviteSelfError,
    GameNotActiveError,
    GameplayNotFoundError,
    HostBusyError,
    InvalidMoveError,
    InvitationNotPendingError,
    NotAParticipantError,
    NotYourTurnError,
    UserBusyError,
)
from gameapi.services.game_engine import (
    apply_move,
    empty_board,
    evaluate_result,
    find_winner_line,
    is_valid_move,
)
from gameapi.services.gameplay_service import GameplayService
from gameapi.services.user_service import UserService

logger = logging.getLogger(__name__)


def _invitation_replaced_event(game_id: str, reason: str) -> dict[str, Any]:
    """Build a replacement notification for a displaced host.

    The payload is intentionally a strict subset of the timeout-expired event, so
    any handler that switches on the reason field continues to work unchanged.
    """
    return {
        "event": "invitation_replaced",
        "payload": {"game_id": game_id, "reason": reason},
    }


def _invitation_promoted_event(game_id: str, host_id: str, host_name: str) -> dict[str, Any]:
    """Build a promotion notification for a queued invitation.

    The payload is identical in shape to invitation_received, allowing the client to
    treat a queued-to-pending promotion as a fresh invitation without special casing.
    """
    return {
        "event": "invitation_promoted",
        "payload": {
            "game_id": game_id,
            "host": {"id": host_id, "name": host_name},
        },
    }


class GameEngineService:
    def __init__(
        self,
        gameplay_service: GameplayService,
        user_service: UserService,
        event_bus: EventBus,
    ) -> None:
        self.gameplay_service = gameplay_service
        self.user_service = user_service
        self.event_bus = event_bus

    async def create_game(self, host_id: str, guest_id: str) -> str:
        """Create a gameplay in pending or queued invitation state."""
        if host_id == guest_id:
            raise CannotInviteSelfError(host_id)

        host_uuid = uuid.UUID(host_id)
        guest_uuid = uuid.UUID(guest_id)
        host_games = await self.gameplay_service._repo.list_by_player(host_uuid)
        if any(
            item.host_player == host_uuid
            and item.guest_player != guest_uuid
            and (item.invitation_state in {"pending", "queued"} or item.match_result is None)
            for item in host_games
        ):
            raise HostBusyError(host_id)

        guest_invitations = await self.gameplay_service._repo.list_by_player(guest_uuid)

        guest_active_game = await self.gameplay_service.find_active_game_for_user(guest_id)
        if guest_active_game is None:
            guest_active_game = next(
                (
                    item
                    for item in guest_invitations
                    if item.guest_player == guest_uuid
                    and item.invitation_state == "accepted"
                    and item.match_result is None
                ),
                None,
            )
        if guest_active_game is not None and guest_active_game.host_player != host_uuid:
            raise UserBusyError(guest_id)

        existing_waiting_invites = any(
            item.guest_player == guest_uuid and item.invitation_state in {"pending", "queued"}
            for item in guest_invitations
        )
        invitation_state = "queued" if existing_waiting_invites else "pending"

        board = empty_board()
        create_data = GameplayCreate(
            host_player=host_id,
            guest_player=guest_id,
            player_turn=host_id,
            invitation_state=invitation_state,
            current_positions=json.dumps({"board": board, "last_move": None}),
            match_result=None,
        )
        gameplay = await self.gameplay_service.create(create_data)
        return gameplay.id

    async def accept_invitation(self, game_id: str, guest_id: str) -> int:
        gameplay = await self.gameplay_service.get_by_id(game_id)
        if not gameplay:
            raise GameplayNotFoundError(game_id)

        if gameplay.guest_player != guest_id:
            raise NotAParticipantError(guest_id, game_id)

        if gameplay.invitation_state not in {"pending", "queued"}:
            raise InvitationNotPendingError(game_id)

        update_data = GameplayUpdate(
            player_turn=gameplay.host_player,
            invitation_state="accepted",
            match_result="null",
        )
        await self.gameplay_service.update(game_id, update_data)
        await self._promote_next_queued_for_guest(guest_id, reason="previous_replaced")
        displaced = await self._replace_displaced_invitations(guest_id, game_id)
        return displaced

    async def reject_invitation(self, game_id: str, guest_id: str) -> None:
        gameplay = await self.gameplay_service.get_by_id(game_id)
        if not gameplay:
            raise GameplayNotFoundError(game_id)

        if gameplay.guest_player != guest_id:
            raise NotAParticipantError(guest_id, game_id)

        if gameplay.invitation_state not in {"pending", "queued"}:
            raise InvitationNotPendingError(game_id)

        update_data = GameplayUpdate(
            invitation_state="rejected",
            match_result=json.dumps({"winner": None, "reason": "rejected"}),
        )
        await self.gameplay_service.update(game_id, update_data)
        await self._promote_next_queued_for_guest(guest_id, reason="previous_rejected")

    async def _replace_displaced_invitations(self, guest_id: str, accepted_game_id: str) -> int:
        """Replace the guest's other pending/queued invitations and notify their hosts.

        Idempotent: already-replaced invitations with reason='target_busy' are skipped.
        """
        guest_uuid = uuid.UUID(guest_id)
        replaced = 0
        for pending_game in await self.gameplay_service._repo.list_by_player(guest_uuid):
            if str(pending_game.id) == accepted_game_id:
                continue
            if pending_game.invitation_state not in {"pending", "queued"}:
                continue

            match_result = pending_game.match_result
            if isinstance(match_result, str):
                try:
                    match_result = json.loads(match_result)
                except json.JSONDecodeError:
                    match_result = None
            if isinstance(match_result, dict) and match_result.get("reason") == "target_busy":
                continue

            await self.gameplay_service.update_invitation_state(
                str(pending_game.id),
                "expired",
                match_result={"winner": None, "reason": "target_busy"},
            )
            host_id = str(pending_game.host_player)
            event = _invitation_replaced_event(str(pending_game.id), "target_busy")
            await self.event_bus.publish(str(pending_game.id), event)
            if host_id:
                await gameplays_manager.send_to(host_id, event)
                logger.info(
                    "Invitation replaced",
                    extra={
                        "event_type": "invitation_replaced",
                        "player_id": host_id,
                        "gameplay_id": str(pending_game.id),
                        "metadata": {"reason": "target_busy", "replaced_by": accepted_game_id},
                    },
                )
            replaced += 1
        return replaced

    async def _promote_next_queued_for_guest(
        self, guest_id: str, *, reason: str = "previous_terminal"
    ) -> None:
        next_game = await self.gameplay_service.find_next_queued_for_guest(guest_id)
        if next_game is None or next_game.invitation_state != "queued":
            return

        await self.gameplay_service.update_invitation_state(
            str(next_game.id),
            "pending",
        )
        host_id = str(next_game.host_player)
        host = await self.user_service.get_by_id(host_id) if host_id else None
        host_name = host.name if host is not None else "Unknown"
        event = _invitation_promoted_event(str(next_game.id), host_id, host_name)
        await self.event_bus.publish(str(next_game.id), event)
        await gameplays_manager.send_to(guest_id, event)
        logger.info(
            "Invitation promoted",
            extra={
                "event_type": "invitation_promoted",
                "player_id": guest_id,
                "gameplay_id": str(next_game.id),
                "metadata": {"host_id": host_id, "reason": reason},
            },
        )

    async def expire_pending_invitations(self, older_than_seconds: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        expired_rows = await self.gameplay_service.find_expired_pending(cutoff)
        count = 0
        for gameplay in expired_rows:
            if gameplay.invitation_state != "pending":
                continue
            if gameplay.match_result is not None:
                continue
            await self.gameplay_service.update_invitation_state(
                str(gameplay.id),
                "expired",
                match_result={"winner": None, "reason": "expired"},
            )
            host_id = str(gameplay.host_player)
            guest_id = str(gameplay.guest_player) if gameplay.guest_player is not None else None
            logger.info(
                "Invitation expired",
                extra={
                    "event_type": "invitation_expired",
                    "player_id": host_id,
                    "gameplay_id": str(gameplay.id),
                    "metadata": {"reason": "timeout"},
                },
            )
            await self.event_bus.publish(
                str(gameplay.id),
                {
                    "event": "invitation_expired",
                    "payload": {"game_id": str(gameplay.id), "reason": "timeout"},
                },
            )
            if host_id:
                await gameplays_manager.send_to(
                    host_id,
                    {
                        "event": "invitation_expired",
                        "payload": {"game_id": str(gameplay.id), "reason": "timeout"},
                    },
                )
            if guest_id:
                await self._promote_next_queued_for_guest(guest_id, reason="previous_expired")
            count += 1
        return count

    async def expire_queued_invitations(self, older_than_seconds: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        expired_rows = await self.gameplay_service.find_expired_queued(cutoff)
        count = 0
        for gameplay in expired_rows:
            if gameplay.invitation_state != "queued":
                continue
            if gameplay.match_result is not None:
                continue
            await self.gameplay_service.update_invitation_state(
                str(gameplay.id),
                "expired",
                match_result={"winner": None, "reason": "expired"},
            )
            host_id = str(gameplay.host_player)
            logger.info(
                "Invitation expired",
                extra={
                    "event_type": "invitation_expired",
                    "player_id": host_id,
                    "gameplay_id": str(gameplay.id),
                    "metadata": {"reason": "timeout"},
                },
            )
            await self.event_bus.publish(
                str(gameplay.id),
                {
                    "event": "invitation_expired",
                    "payload": {"game_id": str(gameplay.id), "reason": "timeout"},
                },
            )
            await gameplays_manager.send_to(
                host_id,
                {
                    "event": "invitation_expired",
                    "payload": {"game_id": str(gameplay.id), "reason": "timeout"},
                },
            )
            if gameplay.guest_player is not None:
                await self._promote_next_queued_for_guest(
                    str(gameplay.guest_player), reason="previous_expired"
                )
            count += 1
        return count

    async def play_move(
        self,
        game_id: str,
        player_id: str,
        row: int,
        col: int,
    ) -> dict[str, Any]:
        gameplay = await self.gameplay_service.get_by_id(game_id)
        if not gameplay:
            raise GameplayNotFoundError(game_id)

        if player_id not in (gameplay.host_player, gameplay.guest_player):
            raise NotAParticipantError(player_id, game_id)

        if gameplay.invitation_state != "accepted" or gameplay.match_result is not None:
            raise GameNotActiveError(game_id)

        if gameplay.player_turn != player_id:
            raise NotYourTurnError(player_id)

        positions = json.loads(gameplay.current_positions)
        board = positions["board"]

        if not is_valid_move(board, row, col):
            raise InvalidMoveError(row, col)

        player_role: Literal["host", "guest"] = (
            "host" if player_id == gameplay.host_player else "guest"
        )
        new_board = apply_move(board, row, col, player_role)

        result = evaluate_result(new_board)
        last_move = {"row": row, "col": col, "player": player_role}
        new_positions = {"board": new_board, "last_move": last_move}

        next_turn = (
            gameplay.guest_player if player_id == gameplay.host_player else gameplay.host_player
        )

        update_data = GameplayUpdate(
            current_positions=json.dumps(new_positions),
            player_turn=next_turn,
            invitation_state="accepted",
            match_result=json.dumps(result) if result else None,
        )
        await self.gameplay_service.update(game_id, update_data)

        if result:
            winner_id: str | None = None
            if result["winner"] == "host":
                winner_id = gameplay.host_player
            elif result["winner"] == "guest":
                winner_id = gameplay.guest_player

            winner_line: list[list[int]] | None = None
            if result["reason"] == "line":
                raw_line = find_winner_line(new_board)
                if raw_line is not None:
                    winner_line = [[r, c] for r, c in raw_line]

            return {
                "event": "game_ended",
                "payload": {
                    "game_id": game_id,
                    "board": new_board,
                    "winner": winner_id,
                    "reason": result["reason"],
                    "winner_line": winner_line,
                },
            }
        else:
            return {
                "event": "board_updated",
                "payload": {"board": new_board, "turn": next_turn, "last_move": last_move},
            }

    async def leave_game(self, game_id: str, player_id: str) -> bool:
        gameplay = await self.gameplay_service.get_by_id(game_id)
        if not gameplay:
            raise GameplayNotFoundError(game_id)

        if player_id not in (gameplay.host_player, gameplay.guest_player):
            return False

        if gameplay.invitation_state == "pending":
            reason = "host_left" if player_id == gameplay.host_player else "guest_left"
            await self.gameplay_service.update_invitation_state(
                game_id,
                "canceled",
                match_result={"winner": None, "reason": reason},
            )
            await self.event_bus.publish(
                game_id,
                {"event": "invitation_canceled", "payload": {"game_id": game_id, "reason": reason}},
            )
            other_player_id = (
                gameplay.guest_player if player_id == gameplay.host_player else gameplay.host_player
            )
            if other_player_id is not None:
                await gameplays_manager.send_to(
                    str(other_player_id),
                    {
                        "event": "invitation_canceled",
                        "payload": {"game_id": game_id, "reason": reason},
                    },
                )
            return False

        if gameplay.invitation_state != "accepted" or gameplay.match_result is not None:
            return False

        opponent_id = (
            gameplay.guest_player if player_id == gameplay.host_player else gameplay.host_player
        )

        update_data = GameplayUpdate(
            invitation_state="accepted",
            match_result=json.dumps({"winner": opponent_id, "reason": "abandon"}),
        )
        await self.gameplay_service.update(game_id, update_data)
        if gameplay.host_player:
            await self._promote_next_queued_for_guest(str(gameplay.host_player))
        if gameplay.guest_player:
            await self._promote_next_queued_for_guest(str(gameplay.guest_player))
        return True
