from fastapi import APIRouter, HTTPException, Response, status

from gameapi.api.deps import CurrentUser, GameplayServiceDep, UserServiceDep
from gameapi.models.gameplay import GameplayDocument
from gameapi.schemas.gameplay import GameplayCreate, GameplayResponse, GameplayUpdate
from gameapi.services import GameplayNotFoundError

router = APIRouter(prefix="/gameplays", tags=["Gameplays"])


def _to_response(gameplay: GameplayDocument) -> GameplayResponse:
    if gameplay.id is None:
        raise RuntimeError("Gameplay document has no _id; was it persisted?")
    return GameplayResponse(
        id=str(gameplay.id),
        current_positions=gameplay.current_positions,
        host_player=gameplay.host_player,
        guest_player=gameplay.guest_player,
        player_turn=gameplay.player_turn,
        match_result=gameplay.match_result,
        created_date=gameplay.created_date,
        updated_date=gameplay.updated_date,
    )


@router.get(
    "",
    response_model=list[GameplayResponse],
    summary="List all gameplays",
)
async def list_gameplays(service: GameplayServiceDep) -> list[GameplayResponse]:
    gameplays = await service.list_all()
    return [_to_response(g) for g in gameplays]


@router.get(
    "/my-gameplays",
    response_model=list[GameplayResponse],
    summary="List gameplays of the authenticated user",
)
async def list_my_gameplays(
    current_user: CurrentUser,
    service: GameplayServiceDep,
) -> list[GameplayResponse]:
    if current_user.id is None:
        raise RuntimeError("Authenticated user has no _id")
    gameplays = await service.list_by_player(str(current_user.id))
    return [_to_response(g) for g in gameplays]


@router.get(
    "/player/{player_id}",
    response_model=list[GameplayResponse],
    summary="List gameplays of a specific player",
)
async def list_gameplays_by_player(
    player_id: str,
    service: GameplayServiceDep,
) -> list[GameplayResponse]:
    gameplays = await service.list_by_player(player_id)
    return [_to_response(g) for g in gameplays]


@router.get(
    "/{gameplay_id}",
    response_model=GameplayResponse,
    summary="Get a gameplay by id",
)
async def get_gameplay(
    gameplay_id: str,
    service: GameplayServiceDep,
) -> GameplayResponse:
    gameplay = await service.get_by_id(gameplay_id)
    if gameplay is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gameplay not found",
        )
    return _to_response(gameplay)


@router.post(
    "",
    response_model=GameplayResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new gameplay",
)
async def create_gameplay(
    payload: GameplayCreate,
    current_user: CurrentUser,
    service: GameplayServiceDep,
    user_service: UserServiceDep,
    response: Response,
) -> GameplayResponse:
    if current_user.id is None:
        raise RuntimeError("Authenticated user has no _id")
    if payload.host_player != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Host player must be the authenticated user",
        )

    host = await user_service.get_by_id(payload.host_player)
    if host is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Host player does not exist",
        )

    if payload.guest_player is not None:
        guest = await user_service.get_by_id(payload.guest_player)
        if guest is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Guest player does not exist",
            )

    gameplay = await service.create(payload)
    response.headers["Location"] = f"/api/gameplays/{gameplay.id}"
    return _to_response(gameplay)


@router.put(
    "/{gameplay_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update a gameplay",
)
async def update_gameplay(
    gameplay_id: str,
    payload: GameplayUpdate,
    current_user: CurrentUser,
    service: GameplayServiceDep,
    user_service: UserServiceDep,
) -> Response:
    if current_user.id is None:
        raise RuntimeError("Authenticated user has no _id")

    gameplay = await service.get_by_id(gameplay_id)
    if gameplay is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gameplay not found",
        )

    user_id = str(current_user.id)
    if gameplay.host_player != user_id and gameplay.guest_player != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only participants can update this gameplay",
        )

    if payload.guest_player is not None:
        guest = await user_service.get_by_id(payload.guest_player)
        if guest is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Guest player does not exist",
            )

    try:
        await service.update(gameplay_id, payload)
    except GameplayNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gameplay not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{gameplay_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a gameplay",
)
async def delete_gameplay(
    gameplay_id: str,
    current_user: CurrentUser,
    service: GameplayServiceDep,
) -> Response:
    if current_user.id is None:
        raise RuntimeError("Authenticated user has no _id")

    gameplay = await service.get_by_id(gameplay_id)
    if gameplay is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gameplay not found",
        )

    if gameplay.host_player != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the host can delete this gameplay",
        )

    try:
        await service.delete(gameplay_id)
    except GameplayNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gameplay not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
