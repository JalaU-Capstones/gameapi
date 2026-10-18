import random
import re
import uuid

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9_-]{1,28}[a-zA-Z0-9])?$")


def sanitize_username(raw: str) -> str:
    """Convert raw input into a username that follows the username character rules."""
    sanitized = raw.replace(" ", "-")
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", sanitized)
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    sanitized = sanitized[:USERNAME_MAX_LENGTH].rstrip("-")
    if len(sanitized) < USERNAME_MIN_LENGTH:
        return ""
    return sanitized


def generate_fallback_username() -> str:
    """Return ``player-`` followed by four hexadecimal characters."""
    return f"player-{uuid.uuid4().hex[:4]}"


def generate_unique_username(base: str, existing_usernames: set[str]) -> str:
    """Return a username unique among existing usernames, ignoring case."""
    username = base[:USERNAME_MAX_LENGTH]
    if len(username) < USERNAME_MIN_LENGTH:
        username = generate_fallback_username()

    existing_lowercase = {value.lower() for value in existing_usernames}
    if username.lower() not in existing_lowercase:
        return username

    prefix = username[: USERNAME_MAX_LENGTH - 4].rstrip("-")
    while True:
        candidate = f"{prefix}-{random.randint(100, 999)}"
        if candidate.lower() not in existing_lowercase:
            return candidate
