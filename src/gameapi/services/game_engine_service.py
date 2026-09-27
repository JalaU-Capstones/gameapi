import json
from typing import Any, Literal

from gameapi.schemas.gameplay import GameplayCreate, GameplayUpdate
from gameapi.services.event_bus import EventBus
from gameapi.services.exceptions import (
    CannotInviteSelfError,
    GameNotActiveError,
    GameplayNotFoundError,
    InvalidMoveError,
    InvitationNotPendingError,
    NotAParticipantError,
    NotYourTurnError,
)
from gameapi.services.game_engine import (
    apply_move,
    empty_board,
    evaluate_result,
    is_valid_move,
)
from gameapi.services.gameplay_service import GameplayService
from gameapi.services.user_service import UserService


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
        """
        Create a gameplay in pending state.
        """
        if host_id == guest_id:
            raise CannotInviteSelfError(host_id)

        board = empty_board()
        create_data = GameplayCreate(
            host_player=host_id,
            guest_player=guest_id,
            player_turn=host_id,
            current_positions=json.dumps({"board": board, "last_move": None}),
            # Workaround: player_turn cannot be None due to DB schema constraints,
            # so we use a specific match_result to indicate pending state.
            match_result=json.dumps({"reason": "pending"}),
        )
        gameplay = await self.gameplay_service.create(create_data)
        return gameplay.id

    async def accept_invitation(self, game_id: str, guest_id: str) -> None:
        gameplay = await self.gameplay_service.get_by_id(game_id)
        if not gameplay:
            raise GameplayNotFoundError(game_id)

        if gameplay.guest_player != guest_id:
            raise NotAParticipantError(guest_id, game_id)

        is_pending = gameplay.match_result and "pending" in gameplay.match_result
        if not is_pending:
            raise InvitationNotPendingError(game_id)

        update_data = GameplayUpdate(
            player_turn=gameplay.host_player,
            match_result="null",  # Evaluates to None in GameplayService.update
        )
        await self.gameplay_service.update(game_id, update_data)

    async def reject_invitation(self, game_id: str, guest_id: str) -> None:
        gameplay = await self.gameplay_service.get_by_id(game_id)
        if not gameplay:
            raise GameplayNotFoundError(game_id)

        if gameplay.guest_player != guest_id:
            raise NotAParticipantError(guest_id, game_id)

        is_pending = gameplay.match_result and "pending" in gameplay.match_result
        if not is_pending:
            raise InvitationNotPendingError(game_id)

        update_data = GameplayUpdate(
            match_result=json.dumps({"winner": None, "reason": "rejected"})
        )
        await self.gameplay_service.update(game_id, update_data)

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

        # Active if match_result is None
        if gameplay.match_result is not None:
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
            match_result=json.dumps(result) if result else None,
        )
        await self.gameplay_service.update(game_id, update_data)

        if result:
            winner_id = None
            if result["winner"] == "host":
                winner_id = gameplay.host_player
            elif result["winner"] == "guest":
                winner_id = gameplay.guest_player

            return {
                "event": "game_ended",
                "payload": {"winner": winner_id, "reason": result["reason"]},
            }
        else:
            return {
                "event": "board_updated",
                "payload": {"board": new_board, "turn": next_turn, "last_move": last_move},
            }

    async def leave_game(self, game_id: str, player_id: str) -> None:
        gameplay = await self.gameplay_service.get_by_id(game_id)
        if not gameplay:
            raise GameplayNotFoundError(game_id)

        if player_id not in (gameplay.host_player, gameplay.guest_player):
            raise NotAParticipantError(player_id, game_id)

        if gameplay.match_result is not None:
            return  # Game already ended or pending

        opponent_id = (
            gameplay.guest_player if player_id == gameplay.host_player else gameplay.host_player
        )

        update_data = GameplayUpdate(
            match_result=json.dumps({"winner": opponent_id, "reason": "abandon"})
        )
        await self.gameplay_service.update(game_id, update_data)
