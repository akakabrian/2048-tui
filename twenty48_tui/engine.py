"""Pure-Python 2048 engine.

Mirrors the shape a SWIG-bound native engine would have (one class, a
`move()` tick, a `state()` snapshot) so the rest of the app looks like
every other tui-game-build project.

The rules match plibither8/2048.cpp's `gameboard.cpp`:

  * A move in direction D iterates the board from the far end of D back
    toward the near end. For each tile, either:
      - **collapse** with an equal tile in the target cell (sum = 2×value,
        and flag the target as `blocked` for the remainder of this move)
      - **shift** into the target cell if it's empty
  * A collapsed tile is marked `blocked=True` so the next tile in the line
    can't re-merge with it (classic "8+8 should not further merge with
    the 16 that was shifted into place earlier this turn").
  * Keep iterating until no collapse/shift happens in a full sweep.

Score increments by the merged value (2+2 → 4 adds 4 to score; 1024+1024
→ 2048 adds 2048). Matches the original Gabriele Cirulli game and 2048.cpp.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Iterator, Literal

Direction = Literal["up", "down", "left", "right"]
DIRECTIONS: tuple[Direction, ...] = ("up", "down", "left", "right")

# Spawn probability of a 4-tile vs a 2-tile on new-tile placement.
# Classic 2048 uses 10% fours, 90% twos.
FOUR_SPAWN_PROB = 0.1

# Default win threshold. Past this, `continue_after_win` keeps the game
# going forever.
WIN_VALUE = 2048


@dataclass
class Tile:
    """A single cell. value=0 is empty. `merged_this_turn` is the 2048.cpp
    `blocked` flag — prevents chain-merges within a single move."""

    value: int = 0
    merged_this_turn: bool = False
    # Animation metadata — set by `move()`, consumed by the renderer, cleared
    # on the next move. (dx, dy) is the slide displacement in grid cells.
    slid_from: tuple[int, int] | None = None
    just_merged: bool = False
    just_spawned: bool = False


@dataclass
class Board:
    """N×N grid of Tiles. Column-major index would be marginal; we use
    row-major (board[y][x]) because the renderer iterates rows."""

    size: int = 4
    grid: list[list[Tile]] = field(default_factory=list)
    score: int = 0

    def __post_init__(self) -> None:
        if not self.grid:
            self.grid = [[Tile() for _ in range(self.size)]
                         for _ in range(self.size)]

    def copy(self) -> "Board":
        b = Board(self.size, grid=[], score=self.score)
        b.grid = [[Tile(t.value) for t in row] for row in self.grid]
        return b

    def cells(self) -> Iterator[tuple[int, int, Tile]]:
        for y, row in enumerate(self.grid):
            for x, t in enumerate(row):
                yield x, y, t

    def empty_cells(self) -> list[tuple[int, int]]:
        return [(x, y) for x, y, t in self.cells() if t.value == 0]

    def at(self, x: int, y: int) -> Tile:
        return self.grid[y][x]

    def values_snapshot(self) -> tuple[tuple[int, ...], ...]:
        return tuple(tuple(t.value for t in row) for row in self.grid)


class Game:
    """The full 2048 game state — board + score + best + undo stack +
    win/continue/over flags. All state mutations go through `move()` or
    `new_game()`."""

    def __init__(self, size: int = 4, win_value: int = WIN_VALUE,
                 rng: random.Random | None = None) -> None:
        self.size = size
        self.win_value = win_value
        self.rng = rng if rng is not None else random.Random()
        self.board = Board(size=size)
        self.best_score: int = 0
        # Undo stack — list of (board_snapshot, score, flags) tuples. The
        # TUI can expose as many undos as it likes; we bound to stop
        # runaway memory in stress tests.
        self._undo: list[tuple[list[list[int]], int, bool, bool]] = []
        self._undo_cap = 256
        # Reached 2048 at least once this game. Once true, we offer
        # "continue" and don't flip game_over until the board is full
        # AND no merges remain.
        self.won = False
        # Player hit "continue after win" — suppresses the win banner.
        self.continued = False
        # Set True once no moves remain.
        self.game_over = False
        # Counters
        self.moves_count = 0
        self.merges_count = 0
        # Seed the board with two tiles to start.
        self._spawn_tile()
        self._spawn_tile()

    # ---- lifecycle ----------------------------------------------------

    def new_game(self) -> None:
        self.board = Board(size=self.size)
        self._undo.clear()
        self.won = False
        self.continued = False
        self.game_over = False
        self.moves_count = 0
        self.merges_count = 0
        self._spawn_tile()
        self._spawn_tile()

    def set_size(self, size: int) -> None:
        """Reset to a fresh board of the given size. Best score is kept
        per-size in the caller (state.py); this method just resets play."""
        self.size = size
        self.new_game()

    # ---- move logic ---------------------------------------------------

    def move(self, direction: Direction) -> bool:
        """Apply one move. Returns True if the board changed (a real move
        happened), False if the move was a no-op (nothing slid or merged).
        Only a real move spawns a new tile and pushes an undo snapshot."""
        if self.game_over:
            return False
        snapshot = self._snapshot()
        board_before = self.board.values_snapshot()

        # Clear per-move flags on every tile so the renderer doesn't see
        # stale animation state.
        for _x, _y, t in self.board.cells():
            t.merged_this_turn = False
            t.slid_from = None
            t.just_merged = False
            t.just_spawned = False

        score_gained, merges = self._slide_and_merge(direction)

        board_after = self.board.values_snapshot()
        if board_before == board_after:
            # No-op — revert per-move bookkeeping and bail.
            return False

        self.board.score += score_gained
        self.merges_count += merges
        self.moves_count += 1

        # Spawn a new tile after every real move.
        spawn = self._spawn_tile()
        if spawn is not None:
            x, y = spawn
            self.board.at(x, y).just_spawned = True

        # Push undo AFTER the move completed successfully.
        self._undo.append(snapshot)
        if len(self._undo) > self._undo_cap:
            self._undo = self._undo[-self._undo_cap:]

        # Win detection — any tile at or above win_value flips `won`.
        # (Only fires the banner once per game; if the player continued,
        # we just keep going.)
        if not self.won:
            for _x, _y, t in self.board.cells():
                if t.value >= self.win_value:
                    self.won = True
                    break

        # Update best score — best score is the max ever hit, including
        # intermediate values (if the player loses, the final score
        # isn't necessarily the peak).
        if self.board.score > self.best_score:
            self.best_score = self.board.score

        # Game-over detection — no empty cells AND no merge-possible pair.
        if not self.board.empty_cells() and not self._any_merges_possible():
            self.game_over = True

        return True

    def _slide_and_merge(self, direction: Direction) -> tuple[int, int]:
        """Apply 2048's slide + merge in one sweep.

        We use an axis-agnostic approach: extract each line in the direction
        of motion as a list of tile references, compact it, and write back.
        This is simpler and faster than the 2048.cpp nested-loop port.

        Returns (score_gained, merge_count)."""
        score_gained = 0
        merges = 0
        for line in self._lines_in_direction(direction):
            # line is a list of Tile references, ordered from the "far"
            # end (where tiles slide TO) to the "near" end. We compact
            # them toward index 0.
            originals = [(t.value, i) for i, t in enumerate(line) if t.value != 0]
            new_values: list[tuple[int, int | None, bool]] = []
            # Each entry is (value, slid_from_index, merged_this_turn)
            i = 0
            while i < len(originals):
                v, origin = originals[i]
                if (i + 1 < len(originals)
                        and originals[i + 1][0] == v):
                    # Merge: pair (i, i+1) → single tile of 2v.
                    merged_value = v * 2
                    # Mark merged; the renderer needs to know the animation.
                    # slid_from: we store the farther-travelling of the pair,
                    # which is the one originally further from the target.
                    new_values.append((merged_value, originals[i + 1][1], True))
                    score_gained += merged_value
                    merges += 1
                    i += 2
                else:
                    new_values.append((v, origin, False))
                    i += 1
            # Write back — first len(new_values) slots get the compacted
            # values, rest are zeroed.
            for j, t in enumerate(line):
                if j < len(new_values):
                    value, origin, did_merge = new_values[j]
                    t.value = value
                    if origin is not None and origin != j:
                        # slid_from is stored in axis-local coords; the
                        # renderer translates back when it knows the axis.
                        t.slid_from = (origin, j)
                    t.just_merged = did_merge
                    t.merged_this_turn = did_merge
                else:
                    t.value = 0
                    t.slid_from = None
                    t.just_merged = False
                    t.merged_this_turn = False
        return score_gained, merges

    def _lines_in_direction(self, direction: Direction) -> list[list[Tile]]:
        """Return a list of lines (each a list of Tile references) that
        should be compacted toward index 0 to realise a move in `direction`.

        For "left", each row read left→right is already in compacted order.
        For "right", reverse each row. For "up", each column read top→bottom.
        For "down", each column reversed."""
        N = self.size
        lines: list[list[Tile]] = []
        if direction == "left":
            for y in range(N):
                lines.append([self.board.at(x, y) for x in range(N)])
        elif direction == "right":
            for y in range(N):
                lines.append([self.board.at(x, y) for x in range(N - 1, -1, -1)])
        elif direction == "up":
            for x in range(N):
                lines.append([self.board.at(x, y) for y in range(N)])
        elif direction == "down":
            for x in range(N):
                lines.append([self.board.at(x, y) for y in range(N - 1, -1, -1)])
        else:
            raise ValueError(f"bad direction {direction!r}")
        return lines

    def _any_merges_possible(self) -> bool:
        """True if any adjacent pair of tiles has equal value. Used for
        game-over detection when the board is full."""
        N = self.size
        g = self.board.grid
        for y in range(N):
            for x in range(N):
                v = g[y][x].value
                if v == 0:
                    return True
                if x + 1 < N and g[y][x + 1].value == v:
                    return True
                if y + 1 < N and g[y + 1][x].value == v:
                    return True
        return False

    # ---- undo ---------------------------------------------------------

    def _snapshot(self) -> tuple[list[list[int]], int, bool, bool]:
        return (
            [[t.value for t in row] for row in self.board.grid],
            self.board.score,
            self.won,
            self.continued,
        )

    def undo(self) -> bool:
        """Pop the last snapshot. Returns True on success. Cannot undo past
        the start of a game (empty stack). Also clears game-over state if
        we were in it — undoing a losing move should give the player a
        chance to play on."""
        if not self._undo:
            return False
        values, score, won, continued = self._undo.pop()
        for y, row in enumerate(values):
            for x, v in enumerate(row):
                t = self.board.at(x, y)
                t.value = v
                t.slid_from = None
                t.just_merged = False
                t.just_spawned = False
                t.merged_this_turn = False
        self.board.score = score
        self.won = won
        self.continued = continued
        self.game_over = False
        # Note: we do NOT decrement moves_count/merges_count — undo is a
        # player-facing mulligan, not a historical rewrite. Matches the
        # 2048.cpp behaviour where stats track attempted moves.
        return True

    def can_undo(self) -> bool:
        return bool(self._undo)

    # ---- win / continue ----------------------------------------------

    def continue_after_win(self) -> None:
        """Suppress the win banner and keep playing. No-op if we haven't
        won yet or the player has already opted to continue."""
        if self.won:
            self.continued = True

    # ---- spawning -----------------------------------------------------

    def _spawn_tile(self) -> tuple[int, int] | None:
        """Place a new 2 or 4 on a random empty cell. Returns (x, y) of the
        spawn, or None if the board was full (shouldn't happen on a legal
        move; _any_merges_possible is supposed to catch it upstream)."""
        empties = self.board.empty_cells()
        if not empties:
            return None
        x, y = self.rng.choice(empties)
        value = 4 if self.rng.random() < FOUR_SPAWN_PROB else 2
        self.board.at(x, y).value = value
        return (x, y)

    # ---- introspection / agent API shim -------------------------------

    def state(self) -> dict:
        """State snapshot — used by the status panel, the agent API (if we
        ever add one), and the QA harness for assertions."""
        return {
            "size": self.size,
            "score": self.board.score,
            "best": self.best_score,
            "moves": self.moves_count,
            "merges": self.merges_count,
            "won": self.won,
            "continued": self.continued,
            "game_over": self.game_over,
            "max_tile": max((t.value for _x, _y, t in self.board.cells()),
                            default=0),
            "values": self.board.values_snapshot(),
            "can_undo": self.can_undo(),
        }

    # ---- serialisation -----------------------------------------------

    def to_dict(self) -> dict:
        """Minimal serialisable state. Separate from state() (which carries
        derived stuff useful for the UI but noisy in persisted files)."""
        return {
            "size": self.size,
            "win_value": self.win_value,
            "score": self.board.score,
            "best": self.best_score,
            "won": self.won,
            "continued": self.continued,
            "moves": self.moves_count,
            "merges": self.merges_count,
            "values": [[t.value for t in row] for row in self.board.grid],
        }

    @classmethod
    def from_dict(cls, data: dict,
                  rng: random.Random | None = None) -> "Game":
        """Rehydrate a Game from to_dict() output. Missing fields default
        to sensible values so old save files still load."""
        size = int(data.get("size", 4))
        g = cls(size=size,
                win_value=int(data.get("win_value", WIN_VALUE)),
                rng=rng)
        # Overwrite the seeded start-of-game state with the saved one.
        values = data.get("values")
        if values:
            for y, row in enumerate(values):
                for x, v in enumerate(row):
                    g.board.at(x, y).value = int(v)
        g.board.score = int(data.get("score", 0))
        g.best_score = int(data.get("best", 0))
        g.won = bool(data.get("won", False))
        g.continued = bool(data.get("continued", False))
        g.moves_count = int(data.get("moves", 0))
        g.merges_count = int(data.get("merges", 0))
        g.game_over = not g.board.empty_cells() and not g._any_merges_possible()
        return g
