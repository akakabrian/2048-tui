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

## 6. Autosave-on-every-move

The engine's `to_dict`/`from_dict` already round-trip everything, so
persisting after each successful move costs ~1 ms (the `json.dump`) and
means a crash or Ctrl-Q loses at most one move. We clear the savegame on
terminal states (game-over or won-without-continue) so relaunching
doesn't immediately pop the "YOU WIN" banner again — those states are
terminal narrative, not positions worth resuming.

`--no-resume` on the command line forces a fresh game even if a save
exists; useful for scripted demos and the QA harness.

## 7. Stage-7 phases implemented vs skipped

Following the `tui-game-build` skill's phased polish. For 2048 we
landed:

* **Phase D (sound)** — synth sine blips for `move`/`merge`/`win`/`over`,
  off by default (`s` toggles; `TWENTY48_SOUND=1` pre-enables). Debounce
  at 120 ms so rapid arrow-mash doesn't spawn 20 `paplay` subprocesses.
* **Phase E (save/load + stats)** — autosave on every move, per-size best
  scores in a `StatsScreen` modal (`t`), confirm dialog on new-game over
  a substantive in-progress game (`n` with score ≥ 100 + moves > 0).
* **Phase F (animation)** — 2 Hz pulse on the status-panel
  win/game-over banner, subtle 2-colour alternation. Board itself stays
  still at idle (it's a small grid — animating would just flicker).

Skipped with rationale:

* **Phase A (UI beauty)** — 2048 is a numeric grid; pattern-cycling and
  landmark glyphs make no sense. The warm browser-2048 palette and tile
  style flash on merge already carry the visual.
* **Phase B (budget / graphs / overlays)** — no sim state worth graphing.
  The stats screen + a full help overlay covers the submenu space.
* **Phase C (agent REST API)** — 2048 has a trivial action space (4
  directions); writing a REST server is more ceremony than a real agent
  needs. If we ever bot it, the engine is importable directly.
* **Phase G (LLM advisor)** — "the optimal move is…" advice on 2048 is
  well-studied and doesn't need Anthropic API spend per consult.

## 8. Gotcha — `_render*` method names on Textual widgets

The skill's gotcha catalog warns against `_render` as a helper-method
name on `Widget` subclasses. Textual 8 also populates a `_render_markup:
bool` attribute on widgets (including `Screen`), so naming a helper
`_render_markup` shadows it with a method that Python then tries to
treat as a bool at attribute access — `TypeError: 'bool' object is not
callable` at the call site. Stick to `_build_*` / `_compose_*` / any
prefix not in the `_render*` family.
