# 2048-tui

Terminal-native 2048. Classic 4×4 tile merger; slide with arrows or `hjkl`,
merge equal tiles to double their value, reach 2048 to win, keep playing
past it for the leaderboard.

Variable board sizes 3×3 through 6×6 (`+` / `-` at runtime, or `--size N`
on the command line). Per-size best scores persist across sessions in
`~/.local/share/2048-tui/state.json`.

## Install / run

```bash
make all     # creates .venv, installs the package
make run     # launches the game
```

Or directly:
```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python play.py --size 4
```

## Keys

| key | action |
|---|---|
| `↑ ↓ ← →` or `k j h l` | slide |
| `u` | undo (256-entry back-stack) |
| `n` | new game (confirms if current score ≥ 100) |
| `c` | continue playing past 2048 |
| `t` | stats modal — per-size best scores |
| `s` | toggle merge sounds (off by default) |
| `+` / `-` | bigger / smaller board (3..6, starts a new game) |
| `?` | help overlay |
| `q` | quit |

The game autosaves after every move to
`~/.local/share/2048-tui/state.json`, so quitting and re-running resumes
where you left off. Pass `--no-resume` on the command line to force a
fresh game.

## Tests

```bash
make test           # full QA suite (~5 s, 35 scenarios)
make test-only PAT=merge   # subset
```

Each scenario saves an SVG screenshot under `tests/out/` for visual diffing.

## Engine

Pure Python. The `engine/` tree vendors
[`plibither8/2048.cpp`](https://github.com/plibither8/2048.cpp) as a
reference implementation only — the 2048 rules are ~60 lines and binding
a native engine via SWIG would add 150+ MB of toolchain complexity for
zero gain. See `DECISIONS.md` for the full rationale and the 2048.cpp
conventions we matched (chain-merge blocked flag, 10% four-spawn
probability, win at 2048).
