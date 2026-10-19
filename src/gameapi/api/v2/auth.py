import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from gameapi.api.deps import (
    AuthHTTPException,
    AuthServiceDep,
    CurrentSidDep,
    CurrentUser,
    GameplayServiceDep,
    SessionRepositoryDep,
)
from gameapi.api.v2.ws.manager import chat_manager, gameplays_manager, presence_manager
from gameapi.core.config import settings
from gameapi.core.idempotency import (
    normalize_registration_identity,
    remember_response,
    replay_response_for,
    request_idempotency_store,
)
from gameapi.core.rate_limit import rate_limit
from gameapi.schemas.auth import LoginRequest, LoginResponse, RefreshResponse, RegisterResponse
from gameapi.schemas.user import UserCreate, UserResponse
from gameapi.services.exceptions import (
    EmailAlreadyExistsError,
    GameInProgressError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UsernameAlreadyExistsError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    auth = settings.auth
    response.set_cookie(
        key=auth.access_cookie_name,
        value=access_token,
        max_age=auth.access_token_expire_minutes * 60,
        path=auth.access_cookie_path,
        domain=auth.cookie_domain,
        secure=auth.cookie_secure,
        httponly=True,
        samesite=auth.cookie_samesite,
    )
    response.set_cookie(
        key=auth.refresh_cookie_name,
        value=refresh_token,
        max_age=auth.refresh_token_expire_days * 86400,
        path=auth.refresh_cookie_path,
        domain=auth.cookie_domain,
        secure=auth.cookie_secure,
        httponly=True,
        samesite=auth.cookie_samesite,
    )


def _clear_auth_cookies(response: Response) -> None:
    auth = settings.auth
    for key, path in [
        (auth.access_cookie_name, auth.access_cookie_path),
        (auth.refresh_cookie_name, auth.refresh_cookie_path),
    ]:
        response.delete_cookie(key=key, path=path, domain=auth.cookie_domain)


@router.post(
    "/login",
    response_model=LoginResponse,
    response_model_by_alias=False,
    summary="Login: sets auth cookies and returns a bearer-compatible access token",
    description=(
        "El login de v2 establece cookies HttpOnly para el access y refresh token. "
        "El access token también se devuelve en el body para compatibilidad con "
        "herramientas que usan Authorization: Bearer. El refresh token nunca se expone "
        "en el JSON para evitar fuga por XSS."
    ),
    responses={429: {"description": "Rate limit exceeded"}},
)
@rate_limit(settings.rate_limit.login)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    service: AuthServiceDep,
) -> LoginResponse:
    try:
        access_token, refresh_token, user, _session, other_active_sessions = await service.login(
            payload.email,
            payload.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    _set_auth_cookies(response, access_token, refresh_token)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
        other_active_sessions=other_active_sessions,
        username_was_auto_generated=user.username_modified_by_system,
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user and log them in",
    responses={429: {"description": "Rate limit exceeded"}},
)
@rate_limit(settings.rate_limit.register_limit)
async def register(
    request: Request,
    response: Response,
    payload: UserCreate,
    service: AuthServiceDep,
) -> RegisterResponse:
    idem_key = request.headers.get("Idempotency-Key")
    identity = normalize_registration_identity(payload.email)
    cache_namespace = "register"
    cached = None
    if idem_key:
        cached = replay_response_for(
            store=request_idempotency_store,
            namespace=cache_namespace,
            key_parts=(identity, idem_key),
        )
        if cached is not None:
            payload_json = cached["payload"]
            response.status_code = cached["status_code"]
            _set_auth_cookies(response, payload_json["access_token"], payload_json["refresh_token"])
            return RegisterResponse.model_validate(payload_json)

    try:
        access_token, refresh_token, user, _session, other_active_sessions = await service.register(
            payload
        )
        result = RegisterResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user, from_attributes=True),
            other_active_sessions=other_active_sessions,
            username_was_auto_generated=user.username_modified_by_system,
        )
        if idem_key:
            remember_response(
                store=request_idempotency_store,
                namespace=cache_namespace,
                key_parts=(identity, idem_key),
                value={
                    "status_code": status.HTTP_201_CREATED,
                    "payload": {
                        "access_token": access_token,
                        "token_type": "bearer",
                        "user": UserResponse.model_validate(user, from_attributes=True).model_dump(
                            mode="json"
                        ),
                        "other_active_sessions": other_active_sessions,
                        "username_was_auto_generated": user.username_modified_by_system,
                        "refresh_token": refresh_token,
                    },
                },
                ttl_seconds=86400,
            )
    except EmailAlreadyExistsError as exc:
        if idem_key:
            cached_error = replay_response_for(
                store=request_idempotency_store,
                namespace=f"{cache_namespace}:error",
                key_parts=(identity, idem_key),
            )
            if cached_error is not None:
                response.status_code = cached_error["status_code"]
                raise HTTPException(cached_error["status_code"], cached_error["detail"]) from exc
        error_payload = {"status_code": 409, "detail": "Email is currently registered"}
        if idem_key:
            remember_response(
                store=request_idempotency_store,
                namespace=f"{cache_namespace}:error",
                key_parts=(identity, idem_key),
                value=error_payload,
                ttl_seconds=86400,
            )
        raise HTTPException(409, "Email is currently registered") from exc
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(409, "Username is already taken") from exc

    _set_auth_cookies(response, access_token, refresh_token)
    return result


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    response_model_by_alias=False,
    summary="Refresh the access token and rotate the refresh token",
    responses={429: {"description": "Rate limit exceeded"}},
)
@rate_limit(settings.rate_limit.refresh)
async def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    refresh_token_cookie: Annotated[
        str | None,
        Cookie(alias=settings.auth.refresh_cookie_name),
    ] = None,
) -> RefreshResponse:
    if refresh_token_cookie is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        access_token, new_refresh_token = await service.refresh(refresh_token_cookie)
    except InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    _set_auth_cookies(response, access_token, new_refresh_token)
    return RefreshResponse(access_token=access_token, token_type="bearer")


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the refresh token and clear auth cookies",
)
async def logout(
    response: Response,
    service: AuthServiceDep,
    refresh_token_cookie: Annotated[
        str | None,
        Cookie(alias=settings.auth.refresh_cookie_name),
    ] = None,
) -> Response:
    if refresh_token_cookie:
        await service.logout(refresh_token_cookie)
    _clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/session/takeover",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Force a takeover of all active websocket sessions for the current user",
    responses={
        401: {"description": "Not authenticated"},
        409: {
            "description": (
                "Takeover is unavailable while a game is in progress "
                "(GAME_IN_PROGRESS), or for legacy tokens without a session "
                "(SESSION_REQUIRED)."
            )
        },
        429: {"description": "Rate limit exceeded"},
    },
)
@rate_limit(settings.rate_limit.session_takeover)
async def takeover_session(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    current_sid: CurrentSidDep,
    session_repo: SessionRepositoryDep,
    gameplay_service: GameplayServiceDep,
) -> Response:
    del request
    if current_sid is None:
        raise AuthHTTPException(409, "A session-bound token is required", "SESSION_REQUIRED")

    if await gameplay_service.find_active_game_for_user(current_user.id) is not None:
        error = GameInProgressError(current_user.id)
        raise AuthHTTPException(
            409,
            str(error),
            "GAME_IN_PROGRESS",
        ) from error

    current_session = await session_repo.get_by_id(UUID(current_sid))
    if current_session is None or current_session.revoked_at is not None:
        raise AuthHTTPException(401, "Session ended", "SESSION_REVOKED")

    revoked_sessions = await session_repo.revoke_all_for_user(
        UUID(current_user.id),
        "session_replaced",
        exclude_session_id=UUID(current_sid),
    )
    for manager in (gameplays_manager, presence_manager, chat_manager):
        await manager.close_sessions_except(current_user.id, current_sid)

    logger.info(
        "Session takeover requested",
        extra={
            "event_type": "session_takeover",
            "player_id": current_user.id,
            "metadata": {"revoked_sessions": revoked_sessions},
        },
    )

    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the current authenticated user",
    responses={429: {"description": "Rate limit exceeded"}},
)
@rate_limit(settings.rate_limit.auth_me)
async def me(request: Request, response: Response, current_user: CurrentUser) -> UserResponse:
    del request
    del response
    return current_user
