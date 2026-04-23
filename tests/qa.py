"""QA harness — drives Twenty48App through the Textual Pilot and asserts
on live engine state.

    python -m tests.qa            # run everything
    python -m tests.qa merge      # subset by substring

Exit code is the number of failures. Each scenario writes an SVG
screenshot under `tests/out/` for visual diffing.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

# Make sure persistence goes to a temp dir during tests — we don't want
# the QA harness stomping on the user's real best-scores.json.
import tempfile as _tempfile
os.environ["XDG_DATA_HOME"] = _tempfile.mkdtemp(prefix="twenty48-qa-")

from twenty48_tui.app import Twenty48App, BoardView  # noqa: E402
from twenty48_tui.engine import Game, Tile  # noqa: E402
from twenty48_tui import state as state_mod  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    fn: Callable[[Twenty48App, "object"], Awaitable[None]]


# ---------- helpers ----------

def set_board(g: Game, values: list[list[int]]) -> None:
    """Overwrite the board with given values and clear the undo stack —
    useful for constructing deterministic test positions."""
    N = g.size
    assert len(values) == N and all(len(r) == N for r in values)
    for y in range(N):
        for x in range(N):
            t = g.board.at(x, y)
            t.value = values[y][x]
            t.slid_from = None
            t.just_merged = False
            t.just_spawned = False
            t.merged_this_turn = False
    g._undo.clear()
    g.won = any(v >= g.win_value for row in values for v in row)
    g.continued = False
    g.game_over = (not g.board.empty_cells()
                   and not g._any_merges_possible())


def row_values(g: Game, y: int) -> list[int]:
    return [g.board.at(x, y).value for x in range(g.size)]


def col_values(g: Game, x: int) -> list[int]:
    return [g.board.at(x, y).value for y in range(g.size)]


# ---------- scenarios ----------

async def s_mount_clean(app, pilot):
    assert app.game is not None
    assert app.board_view is not None
    assert app.status_panel is not None
    # Freshly-mounted game has 2 spawned tiles.
    non_zero = sum(1 for _x, _y, t in app.game.board.cells() if t.value > 0)
    assert non_zero == 2, f"expected 2 starting tiles, got {non_zero}"


async def s_score_starts_zero(app, pilot):
    assert app.game.board.score == 0, app.game.board.score


async def s_board_size_default_four(app, pilot):
    assert app.game.size == 4, app.game.size


async def s_arrow_moves(app, pilot):
    """Slide the board — the values snapshot must change (the move can
    still be a no-op if no tile had room to slide, so we loop through the
    four directions until one changes something)."""
    before = app.game.board.values_snapshot()
    for key in ("left", "right", "up", "down"):
        await pilot.press(key)
        await pilot.pause()
        if app.game.board.values_snapshot() != before:
            return
    # All four were no-ops — implausible on a fresh 2-tile board.
    assert False, f"no direction changed the board: {before}"


async def s_hjkl_move(app, pilot):
    """Vim keys should be aliases for arrows."""
    before = app.game.board.values_snapshot()
    for key in ("h", "l", "k", "j"):
        await pilot.press(key)
        await pilot.pause()
        if app.game.board.values_snapshot() != before:
            return
    assert False, "hjkl all no-op"


async def s_merge_basic_left(app, pilot):
    """Rigged row [2 2 0 0]: slide left → [4 0 0 0] (plus a spawn somewhere)."""
    g = app.game
    N = g.size
    set_board(g, [[2, 2] + [0] * (N - 2)] + [[0] * N] * (N - 1))
    score_before = g.board.score
    await pilot.press("left")
    await pilot.pause()
    # After slide-left: first cell is 4. Score went up by 4.
    assert g.board.at(0, 0).value == 4, row_values(g, 0)
    assert g.board.score == score_before + 4, g.board.score


async def s_merge_chain_guarded(app, pilot):
    """Rigged row [2 2 2 2]: slide left → [4 4 0 0], NOT [8 0 0 0].
    This is the classic blocked-flag regression — 2048.cpp's `blocked` field
    prevents the just-merged 4 from eating the next 4 in the same pass."""
    g = app.game
    N = g.size
    set_board(g, [[2, 2, 2, 2] + [0] * (N - 4)] + [[0] * N] * (N - 1))
    score_before = g.board.score
    await pilot.press("left")
    await pilot.pause()
    row = row_values(g, 0)
    assert row[0] == 4 and row[1] == 4, f"expected [4,4,...], got {row}"
    assert row[2] == 0 or row[3] == 0, (
        f"only one cell should be spawned; got {row}"
    )
    # Score +8 from the two merges (both produce 4).
    assert g.board.score == score_before + 8, g.board.score


async def s_no_op_move_is_no_op(app, pilot):
    """A move that can't slide or merge anything must not spawn a tile
    and must not push undo. Set up the left column already-packed with
    distinct values so a left-arrow is a no-op."""
    g = app.game
    N = g.size
    values = [[0] * N for _ in range(N)]
    # Column 0 = [2,4,8,16] (all distinct, fully left-packed already).
    values[0][0] = 2
    values[1][0] = 4
    values[2][0] = 8
    values[3][0] = 16
    set_board(g, values)
    before = g.board.values_snapshot()
    undo_len_before = len(g._undo)
    moves_before = g.moves_count
    await pilot.press("left")
    await pilot.pause()
    assert g.board.values_snapshot() == before, (
        f"no-op move changed the board: {g.board.values_snapshot()}"
    )
    assert len(g._undo) == undo_len_before, (
        f"no-op move pushed undo: {undo_len_before} → {len(g._undo)}"
    )
    assert g.moves_count == moves_before


async def s_undo_restores_board(app, pilot):
    """After a real move, undo should restore pre-move state exactly."""
    g = app.game
    set_board(g, [
        [2, 2, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ])
    snap = g.board.values_snapshot()
    score_before = g.board.score
    await pilot.press("left")
    await pilot.pause()
    assert g.board.values_snapshot() != snap, "move didn't change board"
    await pilot.press("u")
    await pilot.pause()
    assert g.board.values_snapshot() == snap, (
        f"undo didn't restore: {g.board.values_snapshot()}"
    )
    assert g.board.score == score_before


async def s_undo_no_moves_is_noop(app, pilot):
    """Undo before any move should just flash a message, never crash."""
    # Clean state — no undo entries yet.
    assert not app.game.can_undo()
    await pilot.press("u")
    await pilot.pause()
    # Still clean.
    assert not app.game.can_undo()


async def s_new_game_resets(app, pilot):
    """New-game should clear the board, zero the score, seed 2 tiles,
    and clear the undo stack. Best score is preserved."""
    g = app.game
    # Force-win-like state so we can assert on reset.
    set_board(g, [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
    await pilot.press("left")
    await pilot.pause()
    assert g.can_undo()
    best_before = g.best_score
    await pilot.press("n")
    await pilot.pause()
    assert not g.can_undo(), "undo stack not cleared"
    assert g.board.score == 0, g.board.score
    assert g.best_score == best_before, "best score lost on new game"
    non_zero = sum(1 for _x, _y, t in g.board.cells() if t.value > 0)
    assert non_zero == 2, non_zero


async def s_win_at_2048(app, pilot):
    """Rig 1024 + 1024 side by side, slide, verify win banner fires."""
    g = app.game
    N = g.size
    set_board(g, [[1024, 1024] + [0] * (N - 2)] + [[0] * N] * (N - 1))
    assert not g.won
    await pilot.press("left")
    await pilot.pause()
    assert g.won, "win flag didn't flip at 2048"
    assert g.board.at(0, 0).value == 2048


async def s_continue_after_win(app, pilot):
    """After winning, pressing 'c' lets you keep playing — the continued
    flag flips but won stays true, and further moves don't re-fire the
    banner."""
    g = app.game
    N = g.size
    set_board(g, [[1024, 1024] + [0] * (N - 2)] + [[0] * N] * (N - 1))
    await pilot.press("left")
    await pilot.pause()
    assert g.won
    await pilot.press("c")
    await pilot.pause()
    assert g.continued, "continue flag didn't flip"
    # Another move should not toggle anything weird.
    await pilot.press("right")
    await pilot.pause()
    assert g.won and g.continued


async def s_game_over_detection(app, pilot):
    """Fill a board with all-distinct adjacent tiles (no merges possible)
    and verify game_over fires without a player move (we call the detector
    directly through a no-op move attempt)."""
    g = app.game
    # Checkerboard of distinct values so no adjacent pair matches.
    set_board(g, [
        [2, 4, 2, 4],
        [4, 2, 4, 2],
        [2, 4, 2, 4],
        [4, 2, 4, 2],
    ])
    # Hmm — adjacent pairs are all distinct (2 next to 4 etc.), so this
    # board is actually game-over. Verify detector.
    assert not g._any_merges_possible()
    assert not g.board.empty_cells()
    # Our set_board helper sets game_over itself when the board is full
    # and non-mergeable.
    assert g.game_over


async def s_change_size_up(app, pilot):
    """Press + to grow to 5×5, verify new board and reset state."""
    assert app.game.size == 4
    await pilot.press("plus")
    await pilot.pause()
    assert app.game.size == 5, app.game.size
    # New board, 2 spawned tiles.
    non_zero = sum(1 for _x, _y, t in app.game.board.cells() if t.value > 0)
    assert non_zero == 2, non_zero


async def s_change_size_clamps(app, pilot):
    """Size can't exceed 6 or drop below 3."""
    for _ in range(5):
        await pilot.press("plus")
        await pilot.pause()
    assert app.game.size == 6, app.game.size
    for _ in range(10):
        await pilot.press("minus")
        await pilot.pause()
    assert app.game.size == 3, app.game.size


async def s_help_toggles(app, pilot):
    """? opens the help overlay, any action dismisses it."""
    assert not app.help_overlay.display
    await pilot.press("question_mark")
    await pilot.pause()
    assert app.help_overlay.display, "help didn't open"
    # Sending an arrow while help is showing should only dismiss help,
    # NOT slide the board.
    before = app.game.board.values_snapshot()
    await pilot.press("left")
    await pilot.pause()
    assert not app.help_overlay.display, "help didn't dismiss"
    assert app.game.board.values_snapshot() == before, (
        "first keypress after help slid the board"
    )


async def s_board_renders_tile_values(app, pilot):
    """The rendered strip for the middle sub-row of a tile with a known
    value should contain that value's digits."""
    g = app.game
    set_board(g, [
        [64, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ])
    bv = app.board_view
    bv.refresh()
    await pilot.pause()
    # Find a row that renders tile (0,0)'s middle.
    found = False
    for screen_y in range(bv.size.height):
        strip = bv.render_line(screen_y)
        text = "".join(seg.text for seg in list(strip))
        if "64" in text:
            found = True
            break
    assert found, "rendered board didn't contain '64'"


async def s_tile_styles_have_bg(app, pilot):
    """Every non-empty tile must render with BOTH fg AND bg colors — a
    bare-fg style would regress the palette."""
    from rich.style import Style  # noqa: F401
    g = app.game
    set_board(g, [
        [2, 4, 8, 16],
        [32, 64, 128, 256],
        [512, 1024, 2048, 0],
        [0, 0, 0, 0],
    ])
    bv = app.board_view
    bv.refresh()
    await pilot.pause()
    bg_count = 0
    for screen_y in range(bv.size.height):
        strip = bv.render_line(screen_y)
        for seg in list(strip):
            if seg.style and seg.style.color is not None and seg.style.bgcolor is not None:
                bg_count += 1
    assert bg_count > 10, (
        f"too few tiles rendered with bg: {bg_count}"
    )


async def s_best_score_persists(app, pilot):
    """After a move that raises the score, state.save() should persist
    the new best, and a fresh load() should read it back."""
    g = app.game
    set_board(g, [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
    await pilot.press("left")
    await pilot.pause()
    # Inspect state file directly.
    data = state_mod.load()
    assert data["best_per_size"].get("4", 0) >= 4, (
        f"best not persisted: {data['best_per_size']}"
    )


async def s_spawn_probabilities(app, pilot):
    """Over many spawns, roughly 10% should be 4s (classic ratio).
    Sampling N=1000 with p=0.1 gives σ≈9.5, so ±40 is a comfortable band."""
    from twenty48_tui.engine import Game
    rng = random.Random(1234)
    g = Game(size=4, rng=rng)
    fours = 0
    N = 1000
    for _ in range(N):
        # Wipe the board each iteration so the spawn function always has
        # a full set of empty cells.
        for _x, _y, t in g.board.cells():
            t.value = 0
        spot = g._spawn_tile()
        assert spot is not None
        if g.board.at(*spot).value == 4:
            fours += 1
    assert 50 <= fours <= 150, f"fours={fours} out of 1000 expected ~100"


async def s_serialisation_round_trip(app, pilot):
    """to_dict / from_dict must preserve board, score, and flags."""
    from twenty48_tui.engine import Game
    g = app.game
    set_board(g, [[2, 4, 8, 16], [0, 0, 0, 2], [0, 0, 0, 4], [0, 0, 0, 0]])
    g.board.score = 1234
    g.best_score = 9999
    g.won = False
    blob = g.to_dict()
    g2 = Game.from_dict(blob)
    assert g2.board.values_snapshot() == g.board.values_snapshot()
    assert g2.board.score == 1234
    assert g2.best_score == 9999


async def s_undo_cap(app, pilot):
    """Undo stack caps at 256 — flooding it should not unbounded-grow."""
    g = app.game
    # Hack the cap way down for a fast test.
    g._undo_cap = 5
    g._undo.clear()
    # Pre-fill moves until the cap; use the engine directly (the app UI
    # would be slow via pilot).
    for _ in range(20):
        set_board(g, [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        g.move("left")
    assert len(g._undo) <= 5, f"stack grew past cap: {len(g._undo)}"


async def s_move_all_directions(app, pilot):
    """Each of the four directions must be a valid move on SOME position."""
    from twenty48_tui.engine import Game
    for direction in ("left", "right", "up", "down"):
        g = Game(size=4, rng=random.Random(7))
        if direction == "left":
            set_board(g, [[0, 0, 0, 2]] + [[0]*4]*3)
        elif direction == "right":
            set_board(g, [[2, 0, 0, 0]] + [[0]*4]*3)
        elif direction == "up":
            set_board(g, [[0]*4, [0]*4, [0]*4, [2, 0, 0, 0]])
        elif direction == "down":
            set_board(g, [[2, 0, 0, 0], [0]*4, [0]*4, [0]*4])
        before = g.board.values_snapshot()
        ok = g.move(direction)
        assert ok, f"{direction} was no-op on rigged board"
        assert g.board.values_snapshot() != before


async def s_up_and_down_work(app, pilot):
    """Rigged column [2,2,0,0]^T + up should combine to [4,0,0,0]^T."""
    g = app.game
    N = g.size
    set_board(g, [
        [2, 0, 0, 0],
        [2, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ])
    await pilot.press("up")
    await pilot.pause()
    col0 = col_values(g, 0)
    assert col0[0] == 4, f"expected col[0]==4, got {col0}"
    # Reset and test down.
    set_board(g, [
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [2, 0, 0, 0],
        [2, 0, 0, 0],
    ])
    await pilot.press("down")
    await pilot.pause()
    col0 = col_values(g, 0)
    assert col0[3] == 4, f"expected col[3]==4, got {col0}"


async def s_header_reflects_score(app, pilot):
    """The Textual sub_title should include the current score after a move."""
    g = app.game
    set_board(g, [[2, 2, 0, 0], [0]*4, [0]*4, [0]*4])
    await pilot.press("left")
    await pilot.pause()
    # Force the app to update the header (tick/on_mount normally does).
    app._update_header()
    assert "score" in app.sub_title.lower()


async def s_autosave_persists_game(app, pilot):
    """After a move, the savegame blob should be written to state and
    `load_savegame(state_mod.load())` should return the same board."""
    g = app.game
    set_board(g, [[2, 2, 0, 0], [0]*4, [0]*4, [0]*4])
    await pilot.press("left")
    await pilot.pause()
    # Reload state from disk.
    data = state_mod.load()
    blob = state_mod.load_savegame(data)
    assert blob is not None, "savegame not persisted after move"
    assert blob["size"] == g.size
    # Board values on the persisted blob should match current in-memory.
    assert blob["values"] == g.to_dict()["values"]


async def s_savegame_cleared_on_terminal_state(app, pilot):
    """Win-without-continue and game-over should clear the savegame so a
    relaunch starts fresh, not re-pops the banner."""
    g = app.game
    # Rig a win-next-move position.
    set_board(g, [[1024, 1024, 0, 0], [0]*4, [0]*4, [0]*4])
    await pilot.press("left")
    await pilot.pause()
    assert g.won
    data = state_mod.load()
    assert state_mod.load_savegame(data) is None, (
        "savegame should be cleared after win-without-continue"
    )


async def s_resume_restores_board(app_unused, pilot_unused):
    """A fresh Twenty48App built while state has a savegame should resume
    that board instead of generating a new random start."""
    from twenty48_tui.app import Twenty48App  # noqa: F811
    # Seed the state with a known savegame.
    data = state_mod.load()
    blob = {
        "size": 4,
        "win_value": 2048,
        "score": 999,
        "best": 9999,
        "won": False, "continued": False,
        "moves": 10, "merges": 3,
        "values": [[2, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
    }
    state_mod.store_savegame(data, blob)
    state_mod.save(data)
    # Build a new app — it should resume.
    app2 = Twenty48App(size=4)
    assert app2._resumed, "fresh app with savegame didn't resume"
    assert app2.game.board.score == 999
    assert app2.game.board.at(0, 0).value == 2
    assert app2.game.board.at(3, 0).value == 16
    # Clean up so other scenarios aren't affected.
    data = state_mod.load()
    state_mod.store_savegame(data, None)
    state_mod.save(data)


async def s_no_resume_flag(app_unused, pilot_unused):
    """resume=False should ignore the savegame and start fresh."""
    from twenty48_tui.app import Twenty48App  # noqa: F811
    data = state_mod.load()
    state_mod.store_savegame(data, {
        "size": 4, "win_value": 2048, "score": 111,
        "best": 0, "won": False, "continued": False,
        "moves": 1, "merges": 0,
        "values": [[2]*4]*4,
    })
    state_mod.save(data)
    app2 = Twenty48App(size=4, resume=False)
    assert not app2._resumed, "resume=False still resumed"
    assert app2.game.board.score == 0
    # Tidy up.
    data = state_mod.load()
    state_mod.store_savegame(data, None)
    state_mod.save(data)


async def s_new_game_confirm_modal(app, pilot):
    """Pressing `n` mid-game with a non-trivial score should push a
    ConfirmScreen, not immediately wipe. Answering 'n' (no) keeps the game;
    answering 'y' starts new."""
    from twenty48_tui.screens import ConfirmScreen
    g = app.game
    # Fake a game state with score >= 100 and some moves (the app checks
    # both — score alone isn't enough).
    g.board.score = 500
    g.moves_count = 5
    before = g.board.values_snapshot()
    await pilot.press("n")
    await pilot.pause()
    # Top screen should now be ConfirmScreen.
    assert isinstance(app.screen, ConfirmScreen), (
        f"expected ConfirmScreen, got {type(app.screen).__name__}"
    )
    # Decline.
    await pilot.press("n")
    await pilot.pause()
    # Board should be unchanged.
    assert g.board.values_snapshot() == before, "declined confirm wiped board"
    assert g.board.score == 500


async def s_new_game_confirm_accepts(app, pilot):
    """Pressing `y` on the ConfirmScreen starts a new game."""
    g = app.game
    g.board.score = 500
    g.moves_count = 5
    await pilot.press("n")
    await pilot.pause()
    await pilot.press("y")
    await pilot.pause()
    assert g.board.score == 0, "accepting confirm didn't reset score"


async def s_stats_screen_opens(app, pilot):
    """Pressing `t` should push a StatsScreen; any key dismisses."""
    from twenty48_tui.screens import StatsScreen
    await pilot.press("t")
    await pilot.pause()
    assert isinstance(app.screen, StatsScreen), (
        f"expected StatsScreen, got {type(app.screen).__name__}"
    )
    await pilot.press("escape")
    await pilot.pause()
    assert not isinstance(app.screen, StatsScreen), "stats didn't dismiss"


async def s_sound_toggle(app_unused, pilot_unused):
    """Sounds module: toggle flips enabled; disabled sounds are no-ops;
    debounce drops bursts."""
    from twenty48_tui.sounds import Sounds
    s = Sounds(enabled=False)
    assert not s.enabled
    # Replace system play with a counter so we don't depend on audio.
    calls: list[str] = []
    s._test_hook = lambda name, path: calls.append(name)
    # Disabled — should not call hook.
    s.play("merge")
    assert calls == []
    # Enable (only succeeds if a player is on PATH; if not, skip the
    # enable-side assertions).
    toggled = s.toggle()
    if not s.available:
        return
    assert toggled is True
    s.play("merge")
    assert calls == ["merge"], calls
    # Immediate repeat is debounced.
    s.play("merge")
    assert calls == ["merge"], "debounce failed"


async def s_pulse_alternates_banner(app, pilot):
    """The 2 Hz pulse should alternate `_pulse_phase` so the win banner
    subtly shifts between two bright styles."""
    g = app.game
    # Put into won-not-continued state.
    from tests.qa import set_board as _sb  # avoid shadowing
    _sb(g, [[2048, 0, 0, 0], [0]*4, [0]*4, [0]*4])
    g.won = True
    g.continued = False
    p0 = app.status_panel._pulse_phase
    app._pulse()
    assert app.status_panel._pulse_phase != p0, "pulse didn't flip phase"
    app._pulse()
    assert app.status_panel._pulse_phase == p0, "pulse didn't flip back"


SCENARIOS: list[Scenario] = [
    Scenario("mount_clean", s_mount_clean),
    Scenario("score_starts_zero", s_score_starts_zero),
    Scenario("board_size_default_four", s_board_size_default_four),
    Scenario("arrow_moves", s_arrow_moves),
    Scenario("hjkl_move", s_hjkl_move),
    Scenario("merge_basic_left", s_merge_basic_left),
    Scenario("merge_chain_guarded", s_merge_chain_guarded),
    Scenario("no_op_move_is_no_op", s_no_op_move_is_no_op),
    Scenario("undo_restores_board", s_undo_restores_board),
    Scenario("undo_no_moves_is_noop", s_undo_no_moves_is_noop),
    Scenario("new_game_resets", s_new_game_resets),
    Scenario("win_at_2048", s_win_at_2048),
    Scenario("continue_after_win", s_continue_after_win),
    Scenario("game_over_detection", s_game_over_detection),
    Scenario("change_size_up", s_change_size_up),
    Scenario("change_size_clamps", s_change_size_clamps),
    Scenario("help_toggles", s_help_toggles),
    Scenario("board_renders_tile_values", s_board_renders_tile_values),
    Scenario("tile_styles_have_bg", s_tile_styles_have_bg),
    Scenario("best_score_persists", s_best_score_persists),
    Scenario("spawn_probabilities", s_spawn_probabilities),
    Scenario("serialisation_round_trip", s_serialisation_round_trip),
    Scenario("undo_cap", s_undo_cap),
    Scenario("move_all_directions", s_move_all_directions),
    Scenario("up_and_down_work", s_up_and_down_work),
    Scenario("header_reflects_score", s_header_reflects_score),
    Scenario("autosave_persists_game", s_autosave_persists_game),
    Scenario("savegame_cleared_on_terminal_state", s_savegame_cleared_on_terminal_state),
    Scenario("resume_restores_board", s_resume_restores_board),
    Scenario("no_resume_flag", s_no_resume_flag),
    Scenario("new_game_confirm_modal", s_new_game_confirm_modal),
    Scenario("new_game_confirm_accepts", s_new_game_confirm_accepts),
    Scenario("stats_screen_opens", s_stats_screen_opens),
    Scenario("sound_toggle", s_sound_toggle),
    Scenario("pulse_alternates_banner", s_pulse_alternates_banner),
]


# ---------- driver ----------

async def run_one(scn: Scenario) -> tuple[str, bool, str]:
    app = Twenty48App(size=4)
    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            try:
                await scn.fn(app, pilot)
            except AssertionError as e:
                app.save_screenshot(str(OUT / f"{scn.name}.FAIL.svg"))
                return (scn.name, False, f"AssertionError: {e}")
            except Exception as e:
                app.save_screenshot(str(OUT / f"{scn.name}.ERROR.svg"))
                return (scn.name, False,
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            app.save_screenshot(str(OUT / f"{scn.name}.PASS.svg"))
            return (scn.name, True, "")
    except Exception as e:
        return (scn.name, False,
                f"harness error: {type(e).__name__}: {e}\n{traceback.format_exc()}")


async def main(pattern: str | None = None) -> int:
    scenarios = [s for s in SCENARIOS if not pattern or pattern in s.name]
    if not scenarios:
        print(f"no scenarios match {pattern!r}")
        return 2
    results = []
    for scn in scenarios:
        name, ok, msg = await run_one(scn)
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name}")
        if not ok:
            for line in msg.splitlines():
                print(f"      {line}")
        results.append((name, ok, msg))
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(main(pattern)))
