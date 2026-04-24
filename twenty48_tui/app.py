"""Textual app for 2048-tui."""

from __future__ import annotations

import time

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Static

from . import state as state_mod
from . import tiles
from .engine import DIRECTIONS, Game
from .music import MusicPlayer
from .screens import ConfirmScreen, EndScreen, StatsScreen
from .sounds import SoundBoard


CELL_W = 7
CELL_H = 3
GAP_W = 1
GAP_H = 1


class BoardView(Widget):
    """Renders the NxN tile grid."""

    anim_t: reactive[float] = reactive(1.0)

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self._empty_bg = Style.parse("on rgb(35,30,25)")
        self._gap_style = Style.parse("on rgb(20,17,14)")
        self._flash_merged_until = 0.5

    def on_mount(self) -> None:
        self.refresh()

    def watch_anim_t(self, old: float, new: float) -> None:
        if self.is_mounted:
            self.refresh()

    def board_pixel_size(self) -> tuple[int, int]:
        n = self.game.size
        w = n * CELL_W + (n - 1) * GAP_W
        h = n * CELL_H + (n - 1) * GAP_H
        return w, h

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        height = self.size.height
        board_w, board_h = self.board_pixel_size()
        off_x = max(0, (width - board_w) // 2)
        off_y = max(0, (height - board_h) // 2)
        if y < off_y or y >= off_y + board_h:
            return Strip([Segment(" " * width, self._gap_style)], width)

        local_y = y - off_y
        row_pitch = CELL_H + GAP_H
        tile_y, sub_y = divmod(local_y, row_pitch)
        if sub_y >= CELL_H:
            return Strip(
                [
                    Segment(" " * off_x, self._gap_style),
                    Segment(" " * board_w, self._gap_style),
                    Segment(" " * max(0, width - off_x - board_w), self._gap_style),
                ],
                width,
            )

        segs: list[Segment] = []
        if off_x > 0:
            segs.append(Segment(" " * off_x, self._gap_style))

        n = self.game.size
        middle_sub_row = CELL_H // 2
        for tile_x in range(n):
            t = self.game.board.at(tile_x, tile_y)
            flash = t.just_merged and self.anim_t < self._flash_merged_until
            style = tiles.style_for(t.value, flash=flash) if t.value > 0 else self._empty_bg
            if sub_y == middle_sub_row:
                label = tiles.cell_text(t.value)
                pad_left = (CELL_W - 6) // 2
                pad_right = CELL_W - 6 - pad_left
                segs.append(Segment(" " * pad_left, style))
                segs.append(Segment(label, style))
                segs.append(Segment(" " * pad_right, style))
            else:
                segs.append(Segment(" " * CELL_W, style))
            if tile_x < n - 1:
                segs.append(Segment(" " * GAP_W, self._gap_style))

        right_pad = width - off_x - board_w
        if right_pad > 0:
            segs.append(Segment(" " * right_pad, self._gap_style))
        return Strip(segs, width)


_HELP_TEXT = (
    "[bold]2048 — terminal edition[/]\\n\\n"
    "[bold]Goal[/]  slide tiles until two with the same value collide;\\n"
    "       they merge into one of double the value. First tile to\\n"
    "       reach 2048 wins — but you can keep playing past it.\\n\\n"
    "[bold]Keys[/]\\n"
    "  ↑↓←→ or k/j/h/l   move\\n"
    "  u                 undo\\n"
    "  n                 new game\\n"
    "  c                 continue after win\\n"
    "  t                 stats — per-size best scores\\n"
    "  m                 toggle background music\\n"
    "  s                 toggle sound effects\\n"
    "  +/-               board size up/down (3..6)\\n"
    "  ?                 toggle this help\\n"
    "  q                 quit\\n\\n"
    "[bold]Music credits[/]\\n"
    "  Happy — Alex McCulloch (CC0 1.0)\\n"
    "  Easy Lemon — Kevin MacLeod (CC-BY 4.0)\\n"
    "  Fluffing a Duck — Kevin MacLeod (CC-BY 4.0)\\n\\n"
    "[dim]press any key to dismiss[/]"
)


class HelpOverlay(Static):
    def __init__(self) -> None:
        super().__init__(Text.from_markup(_HELP_TEXT))
        self.border_title = "HELP"
        self.display = False


class Twenty48App(App):
    CSS_PATH = "tui.tcss"
    TITLE = "2048 — Terminal"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_game", "New"),
        Binding("u", "undo", "Undo"),
        Binding("c", "continue_game", "Continue"),
        Binding("m", "toggle_music", "Music"),
        Binding("s", "toggle_sound", "Sound"),
        Binding("t", "stats", "Stats"),
        Binding("question_mark", "toggle_help", "Help"),
        Binding("plus", "change_size(1)", "Size+", show=False),
        Binding("minus", "change_size(-1)", "Size-", show=False),
        Binding("up", "move('up')", "↑", show=False, priority=True),
        Binding("down", "move('down')", "↓", show=False, priority=True),
        Binding("left", "move('left')", "←", show=False, priority=True),
        Binding("right", "move('right')", "→", show=False, priority=True),
        Binding("k", "move('up')", "k", show=False, priority=True),
        Binding("j", "move('down')", "j", show=False, priority=True),
        Binding("h", "move('left')", "h", show=False, priority=True),
        Binding("l", "move('right')", "l", show=False, priority=True),
    ]

    def __init__(
        self,
        size: int = 4,
        *,
        resume: bool = True,
        music: bool = False,
        sound: bool = True,
    ) -> None:
        super().__init__()
        self._state = state_mod.load()
        save_blob = state_mod.load_savegame(self._state) if resume else None
        if save_blob and int(save_blob.get("size", 0)) == size:
            try:
                self.game = Game.from_dict(save_blob)
                self._resumed = True
            except (TypeError, KeyError, ValueError):
                state_mod.store_savegame(self._state, None)
                state_mod.save(self._state)
                self.game = Game(size=size)
                self._resumed = False
        else:
            self.game = Game(size=size)
            self._resumed = False

        self.game.best_score = state_mod.best_for_size(self._state, size)
        self.board_view = BoardView(self.game)
        self.hud_left = Static(id="hud-left")
        self.hud_center = Static(id="hud-center")
        self.hud_right = Static(id="hud-right")
        self.context_line = Static(" ", id="context-line")
        self.help_overlay = HelpOverlay()
        self.help_overlay.id = "help-overlay"
        self.soundboard = SoundBoard(enabled=sound)
        self.music = MusicPlayer(enabled=music)
        self._started_at = time.monotonic()

    def game_state_vector(self):
        from . import rl_hooks

        return rl_hooks.state_vector(self.game)

    def game_reward(
        self,
        prev_score: int = 0,
        prev_game_over: bool = False,
        board_changed: bool = True,
    ) -> float:
        from . import rl_hooks

        return rl_hooks.compute_reward(prev_score, prev_game_over, board_changed, self.game)

    def is_terminal(self) -> bool:
        from . import rl_hooks

        return rl_hooks.is_terminal(self.game)

    def reset_game(self) -> None:
        self.game.new_game()

    def compose(self) -> ComposeResult:
        with Vertical(id="main"):
            with Horizontal(id="hud-row"):
                yield self.hud_left
                yield self.hud_center
                yield self.hud_right
            yield self.board_view
            yield self.context_line
        yield self.help_overlay

    async def on_mount(self) -> None:
        self._started_at = time.monotonic()
        self.music.start()
        self._refresh_hud()
        if self._resumed:
            self._set_context(f"[dim]resumed game — score {self.game.board.score:,}[/]")
        else:
            self._show_hint()
        self.set_interval(1.0, self._refresh_hud)

    async def on_unmount(self) -> None:
        self.music.stop()

    def _elapsed_text(self) -> str:
        sec = int(max(0.0, time.monotonic() - self._started_at))
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _set_context(self, msg: str) -> None:
        self.context_line.update(Text.from_markup(msg))

    def _refresh_hud(self) -> None:
        s = self.game.state()
        self.hud_left.update("[b #ffd45a]2048[/b #ffd45a]")
        self.hud_center.update(
            f"[b]Time[/b] {self._elapsed_text()}   [b]Moves[/b] {s['moves']:,}"
        )
        self.hud_right.update(f"[b]Score[/b] [#ffd45a]{s['score']:,}[/#ffd45a]")
        state_bits = []
        if s["won"] and not s["continued"]:
            state_bits.append("WON")
        elif s["won"] and s["continued"]:
            state_bits.append("continuing")
        if s["game_over"]:
            state_bits.append("GAME OVER")
        suffix = f"  ·  {', '.join(state_bits)}" if state_bits else ""
        self.sub_title = (
            f"score {s['score']:,}  ·  best {s['best']:,}  ·  max {s['max_tile']}{suffix}"
        )
        self.board_view.border_title = f"2048 · {s['size']}×{s['size']}"

    def _show_hint(self) -> None:
        s = self.game.state()
        if s["game_over"]:
            self._set_context("[dim]No moves left · n new game · t stats · q quit[/]")
        elif s["won"] and not s["continued"]:
            self._set_context("[dim]Reached 2048 · c continue · n new game[/]")
        else:
            self._set_context(
                "[dim]←↑→↓ / hjkl move · u undo · n new · t stats · m music · s sound · ? help · q quit[/]"
            )

    def _animate_move(self) -> None:
        self.board_view.anim_t = 0.0

        def step_frame() -> None:
            t = self.board_view.anim_t + 0.25
            if t >= 1.0:
                self.board_view.anim_t = 1.0
                return
            self.board_view.anim_t = t
            self.set_timer(0.03, step_frame)

        self.set_timer(0.03, step_frame)

    def _autosave(self) -> None:
        s = self.game.state()
        if s["game_over"] or (s["won"] and not s["continued"]):
            state_mod.store_savegame(self._state, None)
        else:
            state_mod.store_savegame(self._state, self.game.to_dict())
        self._state["last_size"] = self.game.size
        state_mod.save(self._state)

    def action_move(self, direction: str) -> None:
        if direction not in DIRECTIONS:
            return
        if self.help_overlay.display:
            self._hide_help()
            return
        merges_before = self.game.merges_count
        won_before = self.game.won
        changed = self.game.move(direction)
        if changed:
            self._animate_move()
            state_mod.record_best(self._state, self.game.size, self.game.best_score)
            s = self.game.state()
            if s["won"] and not won_before:
                self.soundboard.play("winwon.wav")
                self.push_screen(
                    EndScreen(self.game, elapsed=self._elapsed_text(), won=True),
                    self._on_end_screen,
                )
            elif s["game_over"]:
                self.push_screen(
                    EndScreen(self.game, elapsed=self._elapsed_text(), won=False),
                    self._on_end_screen,
                )
            elif s["merges"] > merges_before:
                self.soundboard.play("flip.wav")
            self._autosave()
            if s["won"] and not s["continued"]:
                self._set_context("[dim]Reached 2048 · c continue · n new game[/]")
            elif s["game_over"]:
                self._set_context("[dim]No moves left · n new game · t stats · q quit[/]")
            else:
                last = "merged" if s["merges"] > merges_before else "slid"
                self._set_context(f"[dim]{direction}: {last} · u undo · n new · ? help[/]")
        else:
            self.soundboard.play("nomove.wav")
            self._set_context(f"[dim]{direction}: no move · try another direction[/]")
        self._refresh_hud()

    def action_undo(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        if self.game.undo():
            self._set_context("[dim]undo[/]")
            self.board_view.refresh()
        else:
            self._set_context("[dim]nothing to undo[/]")
        self._refresh_hud()

    def action_new_game(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        s = self.game.state()
        if s["moves"] > 0 and s["score"] >= 100 and not s["game_over"]:

            def _after(ok: bool | None) -> None:
                if ok:
                    self._do_new_game()
                else:
                    self._set_context("[dim]kept current game[/]")

            self.push_screen(
                ConfirmScreen(
                    f"Start a new game? Current score [bold]{s['score']:,}[/] will be lost."
                ),
                _after,
            )
            return
        self._do_new_game()

    def _do_new_game(self) -> None:
        self.game.new_game()
        self.soundboard.play("dealwaste.wav")
        self._started_at = time.monotonic()
        state_mod.store_savegame(self._state, None)
        state_mod.save(self._state)
        self.board_view.refresh()
        self._set_context("[dim]new game[/]")
        self._refresh_hud()

    def action_continue_game(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        if self.game.won and not self.game.continued:
            self.game.continue_after_win()
            self._set_context("[dim]continuing past 2048[/]")
            self._refresh_hud()
        else:
            self._set_context("[dim]continue is for after you reach 2048[/]")

    def _on_end_screen(self, result: str | None) -> None:
        if result == "new":
            self._do_new_game()
            return
        if result == "continue":
            if self.game.won and not self.game.continued:
                self.game.continue_after_win()
                self._set_context("[dim]continuing past 2048[/]")
                self._refresh_hud()
            return
        self._show_hint()

    def action_change_size(self, delta: str) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        new_size = max(3, min(6, self.game.size + int(delta)))
        if new_size == self.game.size:
            self._set_context(f"[dim]already at {new_size}×{new_size}[/]")
            return
        state_mod.record_best(self._state, self.game.size, self.game.best_score)
        self.game.set_size(new_size)
        self.game.best_score = state_mod.best_for_size(self._state, new_size)
        self._state["last_size"] = new_size
        state_mod.store_savegame(self._state, None)
        state_mod.save(self._state)
        self._started_at = time.monotonic()
        self.board_view.refresh()
        self._set_context(f"[dim]new {new_size}×{new_size} game[/]")
        self._refresh_hud()

    def action_toggle_help(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
        else:
            self.help_overlay.display = True

    def _hide_help(self) -> None:
        self.help_overlay.display = False

    def action_toggle_sound(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        if not self.soundboard.available:
            self._set_context("[dim]no audio player found (paplay/aplay/afplay)[/]")
            return
        on = self.soundboard.toggle()
        self._set_context(f"[dim]sound {'on' if on else 'off'}[/]")

    def action_toggle_music(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        on = self.music.toggle()
        if not self.music.enabled:
            self._set_context("[dim]music unavailable (missing player/tracks)[/]")
            return
        self._set_context(f"[dim]music {'on' if on else 'off'}[/]")

    def action_stats(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        state_mod.record_best(self._state, self.game.size, self.game.best_score)
        self.push_screen(StatsScreen(self._state))


def run(
    size: int = 4,
    *,
    resume: bool = True,
    music: bool = False,
    sound: bool = True,
) -> None:
    app = Twenty48App(size=size, resume=resume, music=music, sound=sound)
    try:
        app.run()
    finally:
        app.music.stop()
        import sys

        sys.stdout.write("\033[?1000l\033[?1002l\033[?1003l\033[?1006l\033[?1015l\033[?25h")
        sys.stdout.flush()
