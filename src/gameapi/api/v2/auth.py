from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from gameapi.api.deps import AuthServiceDep, CurrentUser
from gameapi.core.config import settings
from gameapi.schemas.auth import LoginRequest, LoginResponse, RefreshResponse
from gameapi.schemas.user import UserCreate, UserResponse
from gameapi.services.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)

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
)
async def login(
    payload: LoginRequest,
    service: AuthServiceDep,
    response: Response,
) -> LoginResponse:
    try:
        access_token, refresh_token, user = await service.login(payload.email, payload.password)
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
    )


@router.post(
    "/register",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user and log them in",
)
async def register(
    payload: UserCreate,
    service: AuthServiceDep,
    response: Response,
) -> LoginResponse:
    try:
        access_token, refresh_token, user = await service.register(payload)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(409, "Email is currently registered") from exc

    _set_auth_cookies(response, access_token, refresh_token)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user, from_attributes=True),
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    response_model_by_alias=False,
    summary="Refresh the access token and rotate the refresh token",
)
async def refresh(
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


@router.get("/me", response_model=UserResponse, summary="Get the current authenticated user")
async def me(current_user: CurrentUser) -> UserResponse:
    return current_user
