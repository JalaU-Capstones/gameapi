from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi import api
from gameapi.api.deps import get_current_user, get_session


async def test_get_session_yields_async_session(db_session: AsyncSession) -> None:
    session_generator = get_session()

    session = await anext(session_generator)

    assert isinstance(session, AsyncSession)
    assert session is not db_session
    await session_generator.aclose()


async def test_get_current_user_rejects_deleted_account(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api.deps, "decode_access_token", lambda _: SimpleNamespace(sub="deleted"))

    class MissingUserService:
        async def get_by_id(self, user_id: str) -> None:
            assert user_id == "deleted"
            return None

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials, MissingUserService())

    assert exc.value.status_code == 401
    assert exc.value.detail == "User no longer exists"
