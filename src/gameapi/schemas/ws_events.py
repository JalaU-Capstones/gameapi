"""Typed schemas for WebSocket events. One class per event payload."""

from pydantic import BaseModel, Field


class CreateGamePayload(BaseModel):
    guest_id: str


class AcceptInvitationPayload(BaseModel):
    game_id: str


class RejectInvitationPayload(BaseModel):
    game_id: str


class PlayMovePayload(BaseModel):
    game_id: str
    row: int = Field(ge=0, le=2)
    col: int = Field(ge=0, le=2)


class LeaveGamePayload(BaseModel):
    game_id: str
