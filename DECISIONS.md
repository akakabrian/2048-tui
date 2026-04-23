# Design decisions — 2048-tui

## 1. Engine: Python reimplementation, with `plibither8/2048.cpp` vendored for reference

The `tui-game-build` skill's canonical stage-2 output is a SWIG-bound native
engine (Micropolis precedent). That's overkill for 2048: the full merge/shift
rule is ~60 lines of Python and has been reimplemented in every language
already. Binding a C++ engine would add 150+ MB of toolchain complexity
(SWIG, a C++ build, a compiled `.so` per platform) for zero algorithmic
gain.

Instead:

- `engine/2048.cpp` — a shallow clone of
  [plibither8/2048.cpp](https://github.com/plibither8/2048.cpp) is vendored
  as a **reference implementation** only. We consulted `gameboard.cpp`
  (`collasped_or_shifted_tilesOnGameboardDataArray`, `shiftTilesOnGameboardDataArray`)
  to confirm the classic convention:
  1. Per move: iterate along the shift direction; for each tile, either
     **collapse** (merge with equal neighbour in the target cell) or **shift**
     (slide into an empty target cell).
  2. Merged tiles are **flagged `blocked`** for the remainder of the move so
     `4 + 4 → 8` in a row can't then eat the newly-shifted `8` next door.
  3. Iterate the board until no collapse / shift happens (typically 1–3 passes).
- The vendored source is **not built**. Nothing on the Python side loads it.
  It's a ~900 kB reference tree and useful for test-vector reproduction.
- `twenty48_tui/engine.py` holds the pure-Python 2048 rules and exposes an
  object-oriented wrapper that mirrors the shape the rest of the TUI would
  expect from a SWIG-bound engine (`sim.move(...)`, `sim.state()`, etc.).

The rest of the skill still applies verbatim (TUI scaffold → QA harness →
perf → polish), and the layout still looks like a skill-canon project —
the stage-2 "one import, one tick, one render" gate just trivially passes
without native build steps.

## 2. Board size

Default 4x4. Variable sizes 3x3 / 5x5 / 6x6 supported via `--size N` flag
and rebindable at runtime. The win threshold stays at **2048** regardless
of size — bigger boards just make it easier / more boring, smaller ones
borderline impossible (3x3 rarely reaches 2048; it's a demo size).

## 3. Persistence

Best-score and settings live in `~/.local/share/2048-tui/state.json` (XDG
data dir). Per-board-size best scores — it's much easier to hit 10k on a
6x6 than a 3x3, and collapsing them into one ranking would reward big
boards unfairly.

## 4. Undo

Unlimited back-stack in memory (bounded at 256 entries — at ~200 bytes per
board snapshot that's 50 kB max, negligible). Cleared on new-game. Each
completed `move()` pushes a snapshot before mutating.

## 5. Textual version pin

`textual>=0.80,<10` — matches the simcity-tui pin. Textual 10 has already
changed a couple of widget internals we depend on (animation frame hook,
`render_line` shape), so we stay under.
