import uuid

import pytest

from gameapi.schemas.gameplay import GameplayUpdate
from gameapi.schemas.user import UserUpdate
from gameapi.services import GameplayService, UserService
from gameapi.services.exceptions import GameplayNotFoundError, UserNotFoundError
from gameapi.services.gameplay_service import _legacy_json_string


async def test_gameplay_service_legacy_json_string_handles_bool_str_and_fallback_types() -> None:
    assert _legacy_json_string(True) == "true"
    assert _legacy_json_string(False) == "false"
    assert _legacy_json_string("hello") == '"hello"'
    assert _legacy_json_string(None) == "null"
    assert _legacy_json_string(3) == "3"
    assert _legacy_json_string([True, None, 3, "x"]) == '[true,null,3,"x"]'
    with pytest.raises(TypeError):
        _legacy_json_string(set())


async def test_gameplay_service_update_nonexistent_uuid(db_session) -> None:
    service = GameplayService(db_session)
    with pytest.raises(GameplayNotFoundError):
        await service.update(str(uuid.uuid4()), GameplayUpdate(match_result='{"winner": "X"}'))


async def test_gameplay_service_delete_nonexistent_uuid(db_session) -> None:
    service = GameplayService(db_session)
    with pytest.raises(GameplayNotFoundError):
        await service.delete(str(uuid.uuid4()))


async def test_user_service_update_nonexistent_uuid(db_session) -> None:
    service = UserService(db_session)
    with pytest.raises(UserNotFoundError):
        await service.update(str(uuid.uuid4()), UserUpdate(name="Updated Name"))


async def test_user_service_delete_nonexistent_uuid(db_session) -> None:
    service = UserService(db_session)
    with pytest.raises(UserNotFoundError):
        await service.delete(str(uuid.uuid4()))


async def test_user_service_ensure_indexes_returns_none(db_session) -> None:
    service = UserService(db_session)
    assert await service.ensure_indexes() is None
