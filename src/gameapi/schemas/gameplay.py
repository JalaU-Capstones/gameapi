import json
from datetime import datetime

from pydantic import field_validator

from gameapi.schemas.base import ApiModel, ObjectIdStr


def _ensure_valid_json(value: str) -> str:
    if not value.strip():
        return value
    try:
        json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("current_positions must be a valid JSON string") from exc
    return value


class GameplayCreate(ApiModel):
    current_positions: str = ""
    host_player: str
    guest_player: str | None = None
    player_turn: str
    match_result: str | None = None

    @field_validator("current_positions")
    @classmethod
    def _check_json(cls, value: str) -> str:
        return _ensure_valid_json(value)


class GameplayUpdate(ApiModel):
    current_positions: str | None = None
    guest_player: str | None = None
    player_turn: str | None = None
    match_result: str | None = None

    @field_validator("current_positions")
    @classmethod
    def _check_json(cls, value: str | None) -> str | None:
        return _ensure_valid_json(value) if value is not None else None


class GameplayResponse(ApiModel):
    id: ObjectIdStr
    current_positions: str
    host_player: str
    guest_player: str | None
    player_turn: str
    match_result: str | None
    created_date: datetime
    updated_date: datetime
