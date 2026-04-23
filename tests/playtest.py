"""Scripted playtest for the critical path.

Runs an in-process Textual Pilot session that demonstrates:
  boot -> movement golden path -> undo -> stats modal -> quit.

Usage:
  python -m tests.playtest
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import tempfile

# Keep playtest persistence isolated from real user state.
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="twenty48-playtest-")

from twenty48_tui.app import Twenty48App
from twenty48_tui.screens import StatsScreen

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


async def run_playtest() -> None:
    app = Twenty48App(size=4, resume=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.save_screenshot(str(OUT / "playtest_01_start.svg"))

        before = app.game.board.values_snapshot()
        for key in ("left", "up", "right", "down", "h", "j", "k", "l"):
            await pilot.press(key)
            await pilot.pause()
            if app.game.board.values_snapshot() != before:
                break
        assert app.game.board.values_snapshot() != before, (
            "golden-path movement didn't change the board"
        )
        assert app.game.moves_count > 0, "move counter did not advance"
        app.save_screenshot(str(OUT / "playtest_02_after_moves.svg"))

        await pilot.press("u")
        await pilot.pause()
        app.save_screenshot(str(OUT / "playtest_03_after_undo.svg"))

        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, StatsScreen), (
            f"expected StatsScreen, got {type(app.screen).__name__}"
        )
        app.save_screenshot(str(OUT / "playtest_04_stats_modal.svg"))

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, StatsScreen), "stats modal did not close"

        await pilot.press("q")
        await pilot.pause()


if __name__ == "__main__":
    asyncio.run(run_playtest())
    print("playtest passed")
