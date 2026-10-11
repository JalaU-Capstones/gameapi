"""v2 Users endpoints — require authentication.

`GET /users` is retained as a deprecated 410 response for privacy, while
registration is handled under `/api/v2/auth/register`.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse

from gameapi.api.deps import CurrentUser, UserServiceDep, get_current_user
from gameapi.schemas.user import PublicUserResponse, UserUpdate
from gameapi.services import EmailAlreadyExistsError, UserNotFoundError

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "",
    response_model=None,
    status_code=status.HTTP_410_GONE,
    deprecated=True,
    summary="List all users (removed)",
    description=(
        "This endpoint was removed for privacy reasons. It exposed personal "
        "information for every user and enabled account enumeration and doxing. "
        "Use GET /api/v2/users/{user_id} for minimal public user details."
    ),
    responses={
        status.HTTP_410_GONE: {
            "description": "Removed for privacy reasons",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"detail": {"type": "string"}},
                        "required": ["detail"],
                    },
                    "example": {"detail": "This endpoint has been removed for privacy reasons."},
                }
            },
        }
    },
)
async def list_users() -> JSONResponse:
    # See the user-list privacy task: prevent account enumeration and doxing.
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={"detail": "This endpoint has been removed for privacy reasons."},
    )


@router.get("/{user_id}", response_model=PublicUserResponse)
async def get_user(
    user_id: str,
    service: UserServiceDep,
) -> PublicUserResponse:
    user = await service.get_by_id(user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return PublicUserResponse.model_validate(user, from_attributes=True)


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
