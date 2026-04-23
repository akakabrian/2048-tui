"""RL exposure hooks for 2048-tui.

Headless — wraps engine.Game. State vector is log2-encoded tile values
(0 empty, 1 = value 2, 2 = value 4, ...) normalised by 16 (log2(65536)).

State vector layout (size=4 → 18 dims total):
    [0 : N*N]   log2(value)/16 per cell, 0 if empty
    [N*N]       score / 10000
    [N*N + 1]   max_tile log2 / 16
    [N*N + 2]   moves / 1000
    [N*N + 3]   game_over flag
    [N*N + 4]   won flag
    [N*N + 5]   free_cells / (N*N)

For size=4 that's 16+6 = 22 dims.

Actions: Discrete(4)
    0 up  1 down  2 left  3 right

Reward:
    score_delta / 20.0   (a 2+2 merge → +0.2, a big merge → more)
    -1.0 on game_over transition
    -0.02 per no-op (move that didn't change the board)
    -0.005 per step
"""

from __future__ import annotations

import math

import numpy as np

from .engine import DIRECTIONS, Game


def state_vector_len(size: int = 4) -> int:
    return size * size + 6


def state_vector(game: Game) -> np.ndarray:
    N = game.size
    out = np.zeros(state_vector_len(N), dtype=np.float32)
    max_tile = 0
    free_cells = 0
    for x, y, t in game.board.cells():
        idx = y * N + x
        v = t.value
        if v > 0:
            out[idx] = math.log2(v) / 16.0
            if v > max_tile:
                max_tile = v
        else:
            free_cells += 1
    out[N * N] = game.board.score / 10000.0
    out[N * N + 1] = (math.log2(max_tile) / 16.0) if max_tile > 0 else 0.0
    out[N * N + 2] = game.moves_count / 1000.0
    out[N * N + 3] = 1.0 if game.game_over else 0.0
    out[N * N + 4] = 1.0 if game.won else 0.0
    out[N * N + 5] = free_cells / float(N * N)
    return out


ACTIONS = ("up", "down", "left", "right")


def apply_action(game: Game, action_idx: int) -> bool:
    d = ACTIONS[int(action_idx) % len(ACTIONS)]
    return game.move(d)   # type: ignore[arg-type]


def compute_reward(prev_score: int, prev_game_over: bool,
                   board_changed: bool, game: Game) -> float:
    score_delta = game.board.score - prev_score
    died = (not prev_game_over) and game.game_over
    noop_penalty = 0.0 if board_changed else -0.02
    return float(score_delta / 20.0
                 + (-1.0 if died else 0.0)
                 + noop_penalty
                 - 0.005)


def is_terminal(game: Game) -> bool:
    return bool(game.game_over)
