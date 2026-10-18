import re
from importlib import import_module
from unittest.mock import Mock

import pytest

from gameapi.core import username
from gameapi.core.username import (
    USERNAME_MAX_LENGTH,
    USERNAME_REGEX,
    generate_fallback_username,
    generate_unique_username,
    sanitize_username,
)

migration = import_module("migrations.versions.0007_username_sanitization")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("John Doe", "John-Doe"),
        ("jane!@#_doe", "jane_doe"),
        ("--player--", "player"),
        ("ab", ""),
        ("a-b", "a-b"),
        ("x" * 40, "x" * USERNAME_MAX_LENGTH),
        ("x" * 29 + "-" + "z", "x" * 29),
    ],
)
def test_sanitize_username(raw: str, expected: str) -> None:
    assert sanitize_username(raw) == expected


def test_sanitize_username_collapses_multiple_hyphens() -> None:
    assert sanitize_username("one   two---three") == "one-two-three"


def test_generate_fallback_username_has_expected_format(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUUID:
        hex = "ab12cd34ef"

    monkeypatch.setattr(username.uuid, "uuid4", lambda: FakeUUID())

    fallback = generate_fallback_username()

    assert fallback == "player-ab12"
    assert USERNAME_REGEX.fullmatch(fallback)


def test_generate_unique_username_is_case_insensitive() -> None:
    assert generate_unique_username("Player", {"PLAYER"}) != "Player"


def test_generate_unique_username_uses_fallback_for_empty_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(username, "generate_fallback_username", lambda: "player-ab12")

    assert generate_unique_username("", set()) == "player-ab12"


def test_generate_unique_username_retries_colliding_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffixes = iter((482, 483))
    monkeypatch.setattr(username.random, "randint", lambda _minimum, _maximum: next(suffixes))

    result = generate_unique_username("john-doe", {"John-Doe", "JOHN-DOE-482"})

    assert result == "john-doe-483"
    assert USERNAME_REGEX.fullmatch(result)


def test_generate_unique_username_truncates_prefix_before_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(username.random, "randint", lambda _minimum, _maximum: 482)

    result = generate_unique_username("x" * 30, {"x" * 30})

    assert result == f'{"x" * 26}-482'
    assert len(result) <= USERNAME_MAX_LENGTH
    assert re.fullmatch(USERNAME_REGEX, result)


def test_username_migration_sanitizes_and_deduplicates_existing_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = Mock()
    result.mappings.return_value.all.return_value = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "John Doe"},
        {"id": 3, "name": "john doe"},
        {"id": 4, "name": "!!!"},
    ]
    connection = Mock()
    connection.execute.side_effect = [result, None, None, None, None]
    operations = Mock()
    operations.get_bind.return_value = connection
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(migration, "generate_fallback_username", lambda: "player-ab12")
    monkeypatch.setattr(username.random, "randint", lambda _minimum, _maximum: 482)

    migration.upgrade()

    updates = [call.args[1] for call in connection.execute.call_args_list[1:]]
    assert [(row["username"], row["modified"]) for row in updates] == [
        ("Alice", False),
        ("John-Doe", True),
        ("john-doe-482", True),
        ("player-ab12", True),
    ]
    operations.drop_column.assert_called_once_with("users", "name")
    operations.create_index.assert_called_once()
