class DomainError(Exception):
    """Base class for domain-level errors."""


class UserNotFoundError(DomainError):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")


class EmailAlreadyExistsError(DomainError):
    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"Email already registered: {email}")


class GameplayNotFoundError(DomainError):
    def __init__(self, gameplay_id: str) -> None:
        self.gameplay_id = gameplay_id
        super().__init__(f"Gameplay not found: {gameplay_id}")
