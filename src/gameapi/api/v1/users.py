from fastapi import APIRouter, HTTPException, Response, status

from gameapi.api.deps import CurrentUser, UserServiceDep
from gameapi.core.security import create_access_token, verify_password
from gameapi.models.user import UserDocument
from gameapi.schemas.token import LoginRequest, LoginResponse
from gameapi.schemas.user import UserCreate, UserResponse, UserUpdate
from gameapi.services import EmailAlreadyExistsError, UserNotFoundError

router = APIRouter(prefix="/users", tags=["Users"])


def _to_response(user: UserDocument) -> UserResponse:
    if user.id is None:
        raise RuntimeError("User document has no _id; was it persisted?")
    return UserResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        register_date=user.register_date,
    )


def _require_self(current_user: UserDocument, user_id: str) -> None:
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
async def create_user(
    payload: UserCreate,
    service: UserServiceDep,
    response: Response,
) -> UserResponse:
    try:
        user = await service.create(payload)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is currently registered",
        ) from exc

    response.headers["Location"] = f"/api/users/{user.id}"
    return _to_response(user)


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List all users",
)
async def list_users(service: UserServiceDep) -> list[UserResponse]:
    users = await service.list_all()
    return [_to_response(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user by id",
)
async def get_user(user_id: str, service: UserServiceDep) -> UserResponse:
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
async def update_user(
    user_id: str,
    payload: UserUpdate,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> Response:
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
async def delete_user(
    user_id: str,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> Response:
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
async def login(payload: LoginRequest, service: UserServiceDep) -> LoginResponse:
    user = await service.get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password):
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
