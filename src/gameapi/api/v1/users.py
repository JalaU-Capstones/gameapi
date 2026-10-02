"""v1 API — Frozen contract.

Paths, request/response shapes, and status codes are stable. The only
allowed evolution is tightening authentication; this is documented as a
deliberate security hardening.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from gameapi.api.deps import CurrentUser, UserServiceDep
from gameapi.core.config import settings
from gameapi.core.rate_limit import rate_limit
from gameapi.core.security import create_access_token, verify_password
from gameapi.db.models.user import User
from gameapi.schemas.token import LoginRequest, LoginResponse
from gameapi.schemas.user import UserCreate, UserResponse, UserUpdate
from gameapi.services import EmailAlreadyExistsError, UserNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


def _to_response(user: User | UserResponse) -> UserResponse:
    if isinstance(user, UserResponse):
        return user
    return UserResponse.model_validate(user)


def _require_self(current_user: UserResponse, user_id: str) -> None:
    if current_user.id is None:
        raise RuntimeError("Authenticated user has no _id")
    if str(current_user.id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own account",
        )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
@rate_limit(settings.rate_limit.register_limit)
async def create_user(
    request: Request,
    payload: UserCreate,
    service: UserServiceDep,
    response: Response,
) -> UserResponse:
    del request
    try:
        user = await service.create(payload)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is currently registered",
        ) from exc

    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return _to_response(user)


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List all users",
)
@rate_limit(settings.rate_limit.authenticated_default)
async def list_users(
    request: Request,
    response: Response,
    _current_user: CurrentUser,
    service: UserServiceDep,
) -> list[UserResponse]:
    del request
    del response
    users = await service.list_all()
    return [_to_response(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user by id",
)
@rate_limit(settings.rate_limit.authenticated_default)
async def get_user(
    request: Request,
    response: Response,
    user_id: str,
    _current_user: CurrentUser,
    service: UserServiceDep,
) -> UserResponse:
    del request
    del response
    user = await service.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return _to_response(user)


@router.put(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update the authenticated user's own account",
)
@rate_limit(settings.rate_limit.authenticated_default)
async def update_user(
    request: Request,
    response: Response,
    user_id: str,
    payload: UserUpdate,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> Response:
    del request
    del response
    _require_self(current_user, user_id)

    try:
        await service.update(user_id, payload)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is currently registered",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the authenticated user's own account",
)
@rate_limit(settings.rate_limit.authenticated_default)
async def delete_user(
    request: Request,
    response: Response,
    user_id: str,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> Response:
    del request
    del response
    _require_self(current_user, user_id)

    try:
        await service.delete(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate a user and return a JWT",
)
@rate_limit(settings.rate_limit.login)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    service: UserServiceDep,
) -> LoginResponse:
    del request
    del response
    user = await service.get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password):
        logger.warning(
            "Login failed",
            extra={
                "event_type": "login_failed",
                "metadata": {"email": payload.email},
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.id is None:
        raise RuntimeError("Persisted user has no _id")

    token = create_access_token(
        subject=str(user.id),
        email=user.email,
        name=user.name,
    )
    return LoginResponse(token=token, user=_to_response(user))
