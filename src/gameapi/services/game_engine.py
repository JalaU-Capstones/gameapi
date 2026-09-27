"""Pure Tic-Tac-Toe rules. No I/O, fully unit-testable."""

from __future__ import annotations

from typing import Literal, TypedDict

Board = list[list[int]]  # 3x3, values 0 (empty), 1 (host), 2 (guest)
CellValue = Literal[0, 1, 2]
Player = Literal["host", "guest"]


class GameResult(TypedDict):
    winner: Player | None
    reason: str


BOARD_SIZE = 3
HOST_CELL = 1
GUEST_CELL = 2


def empty_board() -> Board:
    return [[0 for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]


def is_valid_move(board: Board, row: int, col: int) -> bool:
    """Return True iff (row, col) is within bounds and the cell is empty."""
    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        return False
    return board[row][col] == 0


def apply_move(board: Board, row: int, col: int, player: Player) -> Board:
    """
    Return a NEW board with the move applied. Does NOT validate.
    Caller must check is_valid_move first.
    """
    new_board = [r[:] for r in board]
    new_board[row][col] = HOST_CELL if player == "host" else GUEST_CELL
    return new_board


def check_winner(board: Board) -> Player | None:
    """
    Return "host" or "guest" if there is a winning line, else None.
    Lines: 3 rows, 3 columns, 2 diagonals.
    """
    # Check rows
    for row in range(BOARD_SIZE):
        if board[row][0] != 0 and board[row][0] == board[row][1] == board[row][2]:
            return "host" if board[row][0] == HOST_CELL else "guest"

    # Check columns
    for col in range(BOARD_SIZE):
        if board[0][col] != 0 and board[0][col] == board[1][col] == board[2][col]:
            return "host" if board[0][col] == HOST_CELL else "guest"

    # Check diagonals
    if board[0][0] != 0 and board[0][0] == board[1][1] == board[2][2]:
        return "host" if board[0][0] == HOST_CELL else "guest"

    if board[0][2] != 0 and board[0][2] == board[1][1] == board[2][0]:
        return "host" if board[0][2] == HOST_CELL else "guest"

    return None


def is_board_full(board: Board) -> bool:
    for row in board:
        for cell in row:
            if cell == 0:
                return False
    return True


def evaluate_result(board: Board) -> GameResult | None:
    """
    Return None if the game is still ongoing.
    Return {"winner": <player>, "reason": "line"} if someone won.
    Return {"winner": None, "reason": "draw"} if the board is full with no winner.
    """
    winner = check_winner(board)
    if winner is not None:
        return {"winner": winner, "reason": "line"}

    if is_board_full(board):
        return {"winner": None, "reason": "draw"}

    return None
