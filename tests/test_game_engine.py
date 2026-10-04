from gameapi.services.game_engine import (
    apply_move,
    check_winner,
    empty_board,
    evaluate_result,
    find_winner_line,
    is_board_full,
    is_valid_move,
)


def test_empty_board():
    board = empty_board()
    assert len(board) == 3
    for row in board:
        assert len(row) == 3
        for cell in row:
            assert cell == 0


def test_is_valid_move_empty_cell():
    board = empty_board()
    assert is_valid_move(board, 0, 0) is True
    assert is_valid_move(board, 1, 1) is True
    assert is_valid_move(board, 2, 2) is True


def test_is_valid_move_occupied_cell():
    board = empty_board()
    board[0][0] = 1
    assert is_valid_move(board, 0, 0) is False


def test_is_valid_move_out_of_bounds():
    board = empty_board()
    assert is_valid_move(board, -1, 0) is False
    assert is_valid_move(board, 0, 3) is False
    assert is_valid_move(board, 3, 0) is False
    assert is_valid_move(board, 0, -1) is False


def test_apply_move():
    board = empty_board()
    new_board = apply_move(board, 0, 0, "host")
    assert new_board[0][0] == 1
    assert board[0][0] == 0  # original not mutated

    new_board2 = apply_move(new_board, 1, 1, "guest")
    assert new_board2[1][1] == 2
    assert new_board[1][1] == 0  # original not mutated


def test_check_winner_row_host():
    board = [[1, 1, 1], [0, 2, 0], [2, 0, 0]]
    assert check_winner(board) == "host"


def test_check_winner_col_guest():
    board = [[1, 2, 0], [0, 2, 1], [1, 2, 0]]
    assert check_winner(board) == "guest"


def test_check_winner_diag_host():
    board = [[1, 2, 0], [0, 1, 2], [0, 0, 1]]
    assert check_winner(board) == "host"


def test_check_winner_anti_diag_guest():
    board = [[1, 0, 2], [0, 2, 1], [2, 0, 1]]
    assert check_winner(board) == "guest"


def test_find_winner_line_row_0() -> None:
    board = [[1, 1, 1], [2, 2, 0], [0, 0, 0]]
    assert find_winner_line(board) == [(0, 0), (0, 1), (0, 2)]


def test_find_winner_line_row_1() -> None:
    board = [[2, 0, 0], [1, 1, 1], [2, 0, 0]]
    assert find_winner_line(board) == [(1, 0), (1, 1), (1, 2)]


def test_find_winner_line_row_2() -> None:
    board = [[2, 0, 0], [2, 0, 0], [1, 1, 1]]
    assert find_winner_line(board) == [(2, 0), (2, 1), (2, 2)]


def test_find_winner_line_col_0() -> None:
    board = [[1, 2, 0], [1, 2, 0], [1, 0, 0]]
    assert find_winner_line(board) == [(0, 0), (1, 0), (2, 0)]


def test_find_winner_line_col_1() -> None:
    board = [[0, 1, 2], [0, 1, 2], [2, 1, 0]]
    assert find_winner_line(board) == [(0, 1), (1, 1), (2, 1)]


def test_find_winner_line_col_2() -> None:
    board = [[0, 2, 1], [2, 0, 1], [2, 0, 1]]
    assert find_winner_line(board) == [(0, 2), (1, 2), (2, 2)]


def test_find_winner_line_main_diagonal() -> None:
    board = [[1, 2, 0], [0, 1, 2], [0, 0, 1]]
    assert find_winner_line(board) == [(0, 0), (1, 1), (2, 2)]


def test_find_winner_line_anti_diagonal() -> None:
    board = [[0, 2, 1], [0, 1, 2], [1, 0, 0]]
    assert find_winner_line(board) == [(0, 2), (1, 1), (2, 0)]


def test_find_winner_line_returns_none_when_no_winner() -> None:
    assert find_winner_line(empty_board()) is None


def test_find_winner_line_returns_none_on_draw() -> None:
    board = [[1, 2, 1], [1, 2, 2], [2, 1, 1]]
    assert find_winner_line(board) is None


def test_check_winner_none():
    board = empty_board()
    assert check_winner(board) is None

    board = [[1, 2, 1], [1, 2, 2], [2, 1, 1]]
    assert check_winner(board) is None


def test_is_board_full_false():
    board = empty_board()
    assert is_board_full(board) is False

    board = [[1, 2, 1], [1, 0, 2], [2, 1, 1]]
    assert is_board_full(board) is False


def test_is_board_full_true():
    board = [[1, 2, 1], [1, 2, 2], [2, 1, 1]]
    assert is_board_full(board) is True


def test_evaluate_result_ongoing():
    board = empty_board()
    assert evaluate_result(board) is None


def test_evaluate_result_winner():
    board = [[1, 1, 1], [0, 2, 0], [2, 0, 0]]
    assert evaluate_result(board) == {"winner": "host", "reason": "line"}


def test_evaluate_result_draw():
    board = [[1, 2, 1], [1, 2, 2], [2, 1, 1]]
    assert evaluate_result(board) == {"winner": None, "reason": "draw"}
