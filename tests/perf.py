"""Perf benchmarks — baseline the hot paths so we'd notice a regression.

    python -m tests.perf

Prints median ms for a small fixed number of iterations of:
  * full-board move (slide+merge) — hot path in gameplay
  * render_line on a populated board — hot path in paint
  * full-game loop (move random direction until game over) — end-to-end
"""

from __future__ import annotations

import random
import statistics
import time

from twenty48_tui.engine import DIRECTIONS, Game


def time_iter(label: str, fn, iters: int) -> float:
    """Time `iters` runs, return median ms per run. Warms once."""
    fn()
    samples: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    med = statistics.median(samples)
    print(f"  {label:40s}  {med:8.3f} ms  (median of {iters})")
    return med


def bench_move() -> None:
    rng = random.Random(1)
    g = Game(size=4, rng=rng)
    # Fill some of the board so moves actually do work.
    vals = [[2, 4, 8, 16], [4, 2, 4, 2], [0, 0, 0, 0], [0, 0, 0, 0]]
    for y in range(4):
        for x in range(4):
            g.board.at(x, y).value = vals[y][x]

    def run() -> None:
        g.move(rng.choice(DIRECTIONS))
    time_iter("Game.move() — 4×4", run, iters=2000)


def bench_render_line() -> None:
    from twenty48_tui.app import BoardView
    g = Game(size=4, rng=random.Random(7))
    # Fill with diverse values for a realistic render pass.
    vals = [[2, 4, 8, 16], [32, 64, 128, 256],
            [512, 1024, 2048, 4096], [0, 0, 8, 0]]
    for y in range(4):
        for x in range(4):
            g.board.at(x, y).value = vals[y][x]
    view = BoardView(g)
    # render_line needs the widget size set; we'd normally get that post-
    # mount, but for bench purposes we poke directly.
    from textual.geometry import Size
    view._size = Size(60, 20)  # pyright: ignore[reportPrivateUsage]

    def run() -> None:
        # Render all rows of the board viewport.
        for y in range(20):
            view.render_line(y)
    time_iter("BoardView render all rows — 4×4", run, iters=500)


def bench_random_game() -> None:
    rng = random.Random(1234)

    def run() -> None:
        g = Game(size=4, rng=rng)
        moves = 0
        while not g.game_over and moves < 2000:
            g.move(rng.choice(DIRECTIONS))
            moves += 1
    time_iter("full random game to game_over", run, iters=20)


def bench_6x6() -> None:
    rng = random.Random(3)
    g = Game(size=6, rng=rng)

    def run() -> None:
        g.move(rng.choice(DIRECTIONS))
    time_iter("Game.move() — 6×6", run, iters=2000)


def main() -> None:
    print("2048-tui perf baseline")
    print("=" * 50)
    bench_move()
    bench_6x6()
    bench_render_line()
    bench_random_game()


if __name__ == "__main__":
    main()
