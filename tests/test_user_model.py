import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from gameapi.db.models.user import User
from gameapi.schemas.user import UserUpdate
from gameapi.services.exceptions import UserNotFoundError
from gameapi.services.user_service import UserService


def test_name_property_returns_username() -> None:
    user = User(username="player_one", email="player@example.com", password_hash="hash")

    assert user.name == user.username


def test_name_property_supports_legacy_construction() -> None:
    user = User(name="player_one", email="player@example.com", password_hash="hash")

    assert user.username == "player_one"


async def test_user_service_serializes_username_on_reads_and_noop_updates() -> None:
    user = User(
        id=uuid.uuid4(),
        username="player_one",
        username_modified_by_system=True,
        email="player@example.com",
        password_hash="hash",
        register_date=datetime.now(UTC),
    )
    service = UserService(Mock())
    service._repo.list_all = AsyncMock(return_value=[user])
    service._repo.get_by_id = AsyncMock(return_value=user)

    listed = await service.list_all()
    updated = await service.update(str(user.id), UserUpdate())

    assert listed[0].name == "player_one"
    assert listed[0].username == "player_one"
    assert listed[0].username_modified_by_system is True
    assert updated.username == "player_one"


async def test_user_service_rejects_username_update_for_missing_user() -> None:
    service = UserService(Mock())
    service._repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(UserNotFoundError):
        await service.update(
            "11111111-1111-4111-8111-111111111111",
            UserUpdate(username="new_player"),
        )


async def test_user_service_returns_none_for_invalid_user_id() -> None:
    service = UserService(Mock())

    assert await service.get_by_id("not-a-uuid") is None
    with pytest.raises(UserNotFoundError):
        await service.update("not-a-uuid", UserUpdate(username="new_player"))
