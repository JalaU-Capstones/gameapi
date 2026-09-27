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


class GameNotActiveError(DomainError):
    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        super().__init__(f"Game not active: {game_id}")


class NotYourTurnError(DomainError):
    def __init__(self, player_id: str) -> None:
        self.player_id = player_id
        super().__init__(f"Not your turn: {player_id}")


class InvalidMoveError(DomainError):
    def __init__(self, row: int, col: int) -> None:
        self.row = row
        self.col = col
        super().__init__(f"Invalid move at ({row}, {col})")


class NotAParticipantError(DomainError):
    def __init__(self, player_id: str, game_id: str) -> None:
        self.player_id = player_id
        self.game_id = game_id
        super().__init__(f"Player {player_id} is not a participant in game {game_id}")


class OpponentOfflineError(DomainError):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"Opponent {user_id} is offline")


class CannotInviteSelfError(DomainError):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"Cannot invite yourself: {user_id}")


class InvitationNotPendingError(DomainError):
    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        super().__init__(f"Invitation not pending for game: {game_id}")
