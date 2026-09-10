from base64 import b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from gameapi.core.config import settings


class TokenDecodeError(Exception):
    """Raised when a JWT cannot be validated or decoded."""


def _prehash(password: str) -> bytes:
    return b64encode(sha256(password.encode("utf-8")).digest())


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(_prehash(plain_password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            _prehash(plain_password),
            hashed_password.encode("utf-8"),
        )
    except (TypeError, ValueError):
        return False


class AccessTokenClaims(BaseModel):
    sub: str
    email: EmailStr
    name: str
    jti: str
    iat: int
    exp: int
    iss: str
    aud: str


def create_access_token(*, subject: str, email: str, name: str) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.jwt.expire_minutes)
    claims = {
        "sub": subject,
        "email": email,
        "name": name,
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.jwt.issuer,
        "aud": settings.jwt.audience,
    }
    return str(jwt.encode(claims, settings.jwt.secret_key, algorithm=settings.jwt.algorithm))


def decode_access_token(token: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt.secret_key,
            algorithms=[settings.jwt.algorithm],
            audience=settings.jwt.audience,
            issuer=settings.jwt.issuer,
        )
    except JWTError as exc:
        raise TokenDecodeError(str(exc)) from exc
    return AccessTokenClaims.model_validate(payload)
