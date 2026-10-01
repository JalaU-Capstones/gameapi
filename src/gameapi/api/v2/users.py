"""v2 Users endpoints — require authentication.

v2 intentionally excludes `GET /users` (privacy) and `POST /users` (register,
now under `/api/v2/auth/register`). Only resource operations by id remain.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from gameapi.api.deps import CurrentUser, UserServiceDep, get_current_user
from gameapi.schemas.user import UserResponse, UserUpdate
from gameapi.services import EmailAlreadyExistsError, UserNotFoundError

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    service: UserServiceDep,
) -> UserResponse:
    user = await service.get_by_id(user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return UserResponse.model_validate(user, from_attributes=True)


@router.put("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> Response:
    if str(current_user.id) != user_id:
        raise HTTPException(403, "You can only modify your own account")
    try:
        await service.update(user_id, payload)
    except UserNotFoundError as exc:
        raise HTTPException(404, "User not found") from exc
    except EmailAlreadyExistsError as exc:
        raise HTTPException(409, "Email is currently registered") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> Response:
    if str(current_user.id) != user_id:
        raise HTTPException(403, "You can only delete your own account")
    try:
        await service.delete(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(404, "User not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
