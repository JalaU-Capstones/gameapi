import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.db.models.gameplay import Gameplay
from gameapi.repositories.gameplay_repository import GameplayRepository
from gameapi.schemas.gameplay import GameplayCreate, GameplayResponse, GameplayUpdate
from gameapi.services.exceptions import GameplayNotFoundError


def _legacy_json_string(value: object, *, level: int = 0) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ",".join(_legacy_json_string(item, level=level + 1) for item in value) + "]"
    if isinstance(value, dict):
        items: list[str] = []
        separator = ", " if level == 0 else ","
        colon = ": " if level == 0 else ":"
        for key, item in value.items():
            json_key = json.dumps(str(key))
            items.append(f"{json_key}{colon}{_legacy_json_string(item, level=level + 1)}")
        return "{" + separator.join(items) + "}"
    return json.dumps(value)


class GameplayService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = GameplayRepository(session)

    @staticmethod
    def _to_response(gameplay: Gameplay) -> GameplayResponse:
        return GameplayResponse(
            id=str(gameplay.id),
            current_positions=(
                _legacy_json_string(gameplay.current_positions)
                if gameplay.current_positions
                else ""
            ),
            host_player=str(gameplay.host_player),
            guest_player=str(gameplay.guest_player) if gameplay.guest_player is not None else None,
            player_turn=str(gameplay.player_turn),
            match_result=(
                _legacy_json_string(gameplay.match_result)
                if gameplay.match_result is not None
                else None
            ),
            created_date=gameplay.created_date,
            updated_date=gameplay.updated_date,
        )

    async def list_all(self) -> list[GameplayResponse]:
        gameplays = await self._repo.list_all()
        return [self._to_response(gameplay) for gameplay in gameplays]

    async def get_by_id(self, gameplay_id: str) -> GameplayResponse | None:
        try:
            parsed_id = uuid.UUID(gameplay_id)
        except ValueError:
            return None
        gameplay = await self._repo.get_by_id(parsed_id)
        if gameplay is None:
            return None
        return self._to_response(gameplay)

    async def list_by_player(self, player_id: str) -> list[GameplayResponse]:
        try:
            parsed_id = uuid.UUID(player_id)
        except ValueError:
            return []
        gameplays = await self._repo.list_by_player(parsed_id)
        return [self._to_response(gameplay) for gameplay in gameplays]

    async def create(self, data: GameplayCreate) -> GameplayResponse:
        gameplay = Gameplay(
            current_positions=json.loads(data.current_positions) if data.current_positions else {},
            host_player=uuid.UUID(data.host_player),
            guest_player=uuid.UUID(data.guest_player) if data.guest_player else None,
            player_turn=uuid.UUID(data.player_turn),
            match_result=json.loads(data.match_result) if data.match_result else None,
        )
        created = await self._repo.create(gameplay)
        return self._to_response(created)

    async def update(self, gameplay_id: str, data: GameplayUpdate) -> GameplayResponse:
        try:
            parsed_id = uuid.UUID(gameplay_id)
        except ValueError as exc:
            raise GameplayNotFoundError(gameplay_id) from exc

        gameplay = await self._repo.get_by_id(parsed_id)
        if gameplay is None:
            raise GameplayNotFoundError(gameplay_id)

        for field_name in data.model_fields_set:
            value = getattr(data, field_name)
            if field_name == "current_positions" and value is not None:
                gameplay.current_positions = json.loads(value)
            elif field_name == "match_result" and value is not None:
                gameplay.match_result = json.loads(value)
            elif field_name == "guest_player":
                gameplay.guest_player = uuid.UUID(value) if value is not None else None
            elif field_name == "host_player":
                gameplay.host_player = uuid.UUID(value)
            elif field_name == "player_turn":
                gameplay.player_turn = uuid.UUID(value)
            else:
                setattr(gameplay, field_name, value)

        await self._repo.update(gameplay)
        return self._to_response(gameplay)

    async def delete(self, gameplay_id: str) -> None:
        try:
            parsed_id = uuid.UUID(gameplay_id)
        except ValueError as exc:
            raise GameplayNotFoundError(gameplay_id) from exc

        gameplay = await self._repo.get_by_id(parsed_id)
        if gameplay is None:
            raise GameplayNotFoundError(gameplay_id)
        await self._repo.delete(gameplay)
