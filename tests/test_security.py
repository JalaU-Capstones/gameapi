from gameapi.core.security import (
    TokenDecodeError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password() -> None:
    hashed = hash_password("password123")
    assert hashed.startswith("$2b$")
    assert verify_password("password123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_verify_password_with_malformed_hash_returns_false() -> None:
    assert verify_password("password123", "not-a-bcrypt-hash") is False


def test_create_and_decode_access_token() -> None:
    token = create_access_token(
        subject="65f0a1b2c3d4e5f60718293a",
        email="user@example.com",
        name="User",
    )
    claims = decode_access_token(token)
    assert claims.sub == "65f0a1b2c3d4e5f60718293a"
    assert claims.email == "user@example.com"
    assert claims.name == "User"
    assert claims.iss == "GameAPI"
    assert claims.aud == "GameAPI"
    assert claims.exp > claims.iat


def test_decode_tampered_token_raises() -> None:
    token = create_access_token(
        subject="65f0a1b2c3d4e5f60718293a",
        email="user@example.com",
        name="User",
    )
    try:
        decode_access_token(token + "garbage")
    except TokenDecodeError:
        pass
    else:
        raise AssertionError("Expected TokenDecodeError")
