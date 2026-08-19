#!/usr/bin/env python3
"""Tic Tac Toe game for two players (X and O)."""

def print_board(board):
    print("\n   0   1   2")
    for i, row in enumerate(board):
        print(f"{i}  " + " | ".join(row))
        if i < 2:
            print("  ---+---+---")
    print()

def check_winner(board):
    # Rows & Columns
    for i in range(3):
        if board[i][0] == board[i][1] == board[i][2] != " ":
            return board[i][0]
        if board[0][i] == board[1][i] == board[2][i] != " ":
            return board[0][i]
    # Diagonals
    if board[0][0] == board[1][1] == board[2][2] != " ":
        return board[0][0]
    if board[0][2] == board[1][1] == board[2][0] != " ":
        return board[0][2]
    return None

def is_full(board):
    return all(cell != " " for row in board for cell in row)

def play_game():
    board = [[" " for _ in range(3)] for _ in range(3)]
    current = "X"
    print("\n=== Welcome to Tic Tac Toe ===")
    print("Players take turns. Enter row and column (e.g. 0 1).")

    while True:
        print_board(board)
        print(f"Player {current}'s turn")

        try:
            row, col = map(int, input("Enter row and column: ").split())
        except ValueError:
            print("Invalid input. Please enter two numbers separated by a space.")
            continue

        if not (0 <= row <= 2 and 0 <= col <= 2):
            print("Coordinates out of range. Use 0, 1, or 2.")
            continue

        if board[row][col] != " ":
            print("Cell already taken. Choose another.")
            continue

        board[row][col] = current

        winner = check_winner(board)
        if winner:
            print_board(board)
            print(f"🎉 Player {winner} wins!")
            break

        if is_full(board):
            print_board(board)
            print("It's a tie! Well played both.")
            break

        current = "O" if current == "X" else "X"

if __name__ == "__main__":
    play_game()
