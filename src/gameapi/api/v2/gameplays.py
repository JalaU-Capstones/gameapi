"""v2 Gameplays endpoints.

Only read operations remain in REST. Real-time creation, moves, and
abandonment happen over the WebSocket channel (`/api/v2/ws/gameplays`).
"""

from fastapi import APIRouter, Depends, HTTPException, status

from gameapi.api.deps import CurrentUser, GameplayServiceDep, get_current_user
from gameapi.schemas.gameplay import GameplayResponse

router = APIRouter(
    prefix="/gameplays",
    tags=["Gameplays"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/my-gameplays", response_model=list[GameplayResponse])
async def list_my_gameplays(
    current_user: CurrentUser,
    service: GameplayServiceDep,
) -> list[GameplayResponse]:
    if current_user.id is None:
        raise RuntimeError("Authenticated user has no _id")
    gameplays = await service.list_by_player(str(current_user.id))
    return [GameplayResponse.model_validate(g, from_attributes=True) for g in gameplays]


@router.get("/{gameplay_id}", response_model=GameplayResponse)
async def get_gameplay(
    gameplay_id: str,
    current_user: CurrentUser,
    service: GameplayServiceDep,
) -> GameplayResponse:
    gameplay = await service.get_by_id(gameplay_id)
    if gameplay is None:
        raise HTTPException(404, "Gameplay not found")
    user_id = str(current_user.id)
    if user_id not in (gameplay.host_player, gameplay.guest_player):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a participant in this gameplay")
    return GameplayResponse.model_validate(gameplay, from_attributes=True)
