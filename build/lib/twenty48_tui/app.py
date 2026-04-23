"""Textual app for 2048-tui.

Layout: BoardView takes most of the screen, a side panel shows score /
best / hint text, a status bar under the board shows the current
game-state verbose string (last move / win / game-over).

Keys:
  ↑/↓/←/→ or k/j/h/l : move
  u                  : undo
  n                  : new game
  c                  : continue after win (dismisses win banner)
  + / -              : board size up / down (3..6) — starts a new game
  ?                  : help overlay
  q                  : quit
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Footer, Header, Static

from . import tiles
from .engine import DIRECTIONS, Direction, Game
from . import state as state_mod
from .screens import ConfirmScreen, StatsScreen
from .sounds import Sounds


# Visual cell dimensions. Every cell is `CELL_W` columns × `CELL_H` rows.
# We draw a middle-line-with-number design: top/bot padding rows of
# the cell background, the number centered on the middle row. Classic
# browser-2048 feel.
CELL_W = 7
CELL_H = 3
# A 1-col gap between cells reads as a true grid rather than a painted
# block. Horizontal & vertical gaps for symmetry.
GAP_W = 1
GAP_H = 1


class BoardView(Widget):
    """Renders the NxN tile grid. Full-viewport refresh per move
    (the grid is small — 4×4 is 16 cells — so row-level invalidation is
    pointless overkill)."""

    # Animation progress, 0 → 1. Set to 0 by the app right after a move,
    # ticked up to 1 over ~120 ms by a timer, triggering refresh each step.
    anim_t: reactive[float] = reactive(1.0)

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        # Pre-parsed styles — Style.parse() on every cell every frame is
        # slow, so cache at init and rebuild only on size change (since
        # the grid dims don't change per-tile).
        self._empty_bg = Style.parse("on rgb(35,30,25)")
        self._gap_style = Style.parse("on rgb(20,17,14)")
        # "Just merged" flash visibility — the renderer shows a bright
        # pulse on merged tiles for the first ~half of the animation.
        self._flash_merged_until = 0.5

    def on_mount(self) -> None:
        self.refresh()

    def watch_anim_t(self, old: float, new: float) -> None:
        if self.is_mounted:
            self.refresh()

    # --- sizing ---------------------------------------------------------

    def board_pixel_size(self) -> tuple[int, int]:
        """Total cells × cells on screen, excluding the outer padding."""
        N = self.game.size
        w = N * CELL_W + (N - 1) * GAP_W
        h = N * CELL_H + (N - 1) * GAP_H
        return w, h

    # --- render_line ----------------------------------------------------

    def render_line(self, y: int) -> Strip:
        """Textual calls this once per visible row. We centre the board
        in the widget, clear the rest with the background style."""
        width = self.size.width
        height = self.size.height
        board_w, board_h = self.board_pixel_size()
        # Centre offset.
        off_x = max(0, (width - board_w) // 2)
        off_y = max(0, (height - board_h) // 2)
        # Outside the board region → full-width blank of the widget bg.
        if y < off_y or y >= off_y + board_h:
            return Strip([Segment(" " * width, self._gap_style)], width)

        local_y = y - off_y
        # Which tile row are we in, and which sub-row (0..CELL_H-1) within it?
        row_pitch = CELL_H + GAP_H
        tile_y, sub_y = divmod(local_y, row_pitch)
        if sub_y >= CELL_H:
            # Gap row — just the background across the whole board width.
            return Strip([
                Segment(" " * off_x, self._gap_style),
                Segment(" " * board_w, self._gap_style),
                Segment(" " * max(0, width - off_x - board_w), self._gap_style),
            ], width)

        segs: list[Segment] = []
        if off_x > 0:
            segs.append(Segment(" " * off_x, self._gap_style))

        N = self.game.size
        middle_sub_row = CELL_H // 2
        for tile_x in range(N):
            t = self.game.board.at(tile_x, tile_y)
            flash = t.just_merged and self.anim_t < self._flash_merged_until
            style = (tiles.style_for(t.value, flash=flash)
                     if t.value > 0 else self._empty_bg)
            # Draw the sub-row.
            if sub_y == middle_sub_row:
                label = tiles.cell_text(t.value)
                # CELL_W is 7, cell_text gives 6 wide — pad each side a
                # half to fit. We pre-pad 1 char left of the 6-wide label.
                pad_left = (CELL_W - 6) // 2
                pad_right = CELL_W - 6 - pad_left
                segs.append(Segment(" " * pad_left, style))
                segs.append(Segment(label, style))
                segs.append(Segment(" " * pad_right, style))
            else:
                segs.append(Segment(" " * CELL_W, style))
            if tile_x < N - 1:
                segs.append(Segment(" " * GAP_W, self._gap_style))

        right_pad = width - off_x - board_w
        if right_pad > 0:
            segs.append(Segment(" " * right_pad, self._gap_style))
        return Strip(segs, width)


class StatusPanel(Static):
    """Side panel with score/best/moves, win/over banner, and controls."""

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self.border_title = "SCORE"
        self._last_snapshot: tuple | None = None
        # Toggled every pulse tick; used to alternate the win/game-over
        # banner between two bright styles so the banner draws the eye
        # without being a hard blink.
        self._pulse_phase = False

    def refresh_panel(self, *, force: bool = False) -> None:
        s = self.game.state()
        # `force` is set by the 2 Hz pulse so the banner alternates even
        # when no underlying state changed. We flip the phase on each
        # forced call.
        if force:
            self._pulse_phase = not self._pulse_phase
        snapshot = (s["score"], s["best"], s["moves"], s["merges"],
                    s["max_tile"], s["won"], s["continued"], s["game_over"],
                    s["size"], s["can_undo"], self._pulse_phase if
                    (s["won"] and not s["continued"]) or s["game_over"] else None)
        if not force and snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot
        t = Text()
        t.append("Score     ", style="bold")
        t.append(f"{s['score']:>8,}\n", style="bold rgb(230,155,15)")
        t.append("Best      ", style="bold")
        t.append(f"{s['best']:>8,}\n", style="bold rgb(200,170,40)")
        t.append(f"Size      {s['size']}×{s['size']}\n")
        t.append(f"Moves     {s['moves']:>8,}\n")
        t.append(f"Merges    {s['merges']:>8,}\n")
        t.append(f"Max tile  {s['max_tile']:>8,}\n")
        t.append("\n")
        if s["game_over"]:
            bg = "rgb(180,40,40)" if self._pulse_phase else "rgb(140,20,20)"
            t.append("  GAME OVER  \n", style=f"bold white on {bg}")
            t.append("press [bold]n[/] to start a new game\n")
        elif s["won"] and not s["continued"]:
            bg = "rgb(230,155,15)" if self._pulse_phase else "rgb(255,190,40)"
            t.append("  YOU WIN!  \n", style=f"bold black on {bg}")
            t.append("press [bold]c[/] to continue past 2048\n")
            t.append("or [bold]n[/] for a new game\n")
        else:
            t.append("arrows / hjkl move\n", style="dim")
            t.append("u undo  n new  c continue\n", style="dim")
            t.append("+/- size  t stats  s sound\n", style="dim")
            t.append("? help  q quit\n", style="dim")
        self.update(t)


class FlashBar(Static):
    """One-line transient message — 'merged to 64', 'no move', 'new game'."""

    def set_message(self, msg: str) -> None:
        self.update(Text.from_markup(msg))


_HELP_TEXT = (
    "[bold]2048 — terminal edition[/]\n\n"
    "[bold]Goal[/]  slide tiles until two with the same value collide;\n"
    "       they merge into one of double the value. First tile to\n"
    "       reach 2048 wins — but you can keep playing past it.\n\n"
    "[bold]Keys[/]\n"
    "  ↑↓←→ or k/j/h/l   move\n"
    "  u                 undo (unlimited-ish, 256 back-stack)\n"
    "  n                 new game (confirms if mid-game)\n"
    "  c                 continue after win (dismisses banner)\n"
    "  t                 stats — per-size best scores\n"
    "  s                 toggle merge sounds\n"
    "  +/-               board size up/down (3..6)\n"
    "  ?                 toggle this help\n"
    "  q                 quit\n\n"
    "[bold]Scoring[/]  each merge adds the new tile's value to your\n"
    "           score. Per-size best scores are kept separately —\n"
    "           a big board is easier than a small one.\n\n"
    "[bold]Autosave[/] the current game is persisted after every move,\n"
    "            so quitting and re-running resumes where you left off.\n\n"
    "[dim]press any key to dismiss[/]"
)


class HelpOverlay(Static):
    """One-screen help — shown when the player presses ?. Non-modal (just
    a boxed widget that covers the center), dismissed by any key.

    We pass the markup string to super() instead of calling update() from
    __init__ — Textual 8+ binds the Static's visual to the active App
    inside update(), which raises NoActiveAppError at construction time."""

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
        Binding("s", "toggle_sound", "Sound"),
        Binding("t", "stats", "Stats"),
        Binding("question_mark", "toggle_help", "Help"),
        Binding("plus", "change_size(1)", "Size+", show=False),
        Binding("minus", "change_size(-1)", "Size-", show=False),
        # Movement — arrows and vim keys, both priority so the BoardView
        # doesn't eat them (it's a Widget not ScrollView but playing safe).
        Binding("up",    "move('up')",    "↑", show=False, priority=True),
        Binding("down",  "move('down')",  "↓", show=False, priority=True),
        Binding("left",  "move('left')",  "←", show=False, priority=True),
        Binding("right", "move('right')", "→", show=False, priority=True),
        Binding("k", "move('up')",    "k", show=False, priority=True),
        Binding("j", "move('down')",  "j", show=False, priority=True),
        Binding("h", "move('left')",  "h", show=False, priority=True),
        Binding("l", "move('right')", "l", show=False, priority=True),
    ]

    def __init__(self, size: int = 4, *, resume: bool = True) -> None:
        super().__init__()
        self._state = state_mod.load()
        # Resume an in-progress savegame if one matches the requested size.
        # Pass --no-resume (resume=False) to always start fresh.
        save_blob = state_mod.load_savegame(self._state) if resume else None
        if save_blob and int(save_blob.get("size", 0)) == size:
            try:
                self.game = Game.from_dict(save_blob)
                self._resumed = True
            except (TypeError, KeyError, ValueError):
                # Bad save — discard and start fresh.
                state_mod.store_savegame(self._state, None)
                state_mod.save(self._state)
                self.game = Game(size=size)
                self._resumed = False
        else:
            self.game = Game(size=size)
            self._resumed = False
        self.game.best_score = state_mod.best_for_size(self._state, size)
        self.board_view = BoardView(self.game)
        self.status_panel = StatusPanel(self.game)
        self.flash_bar = FlashBar(" ", id="flash-bar")
        self.help_overlay = HelpOverlay()
        self.help_overlay.id = "help-overlay"
        self.sounds = Sounds()

    # --- RL hooks (headless; no Textual required) ----------------------

    def game_state_vector(self):
        from . import rl_hooks
        return rl_hooks.state_vector(self.game)

    def game_reward(self, prev_score: int = 0,
                    prev_game_over: bool = False,
                    board_changed: bool = True) -> float:
        from . import rl_hooks
        return rl_hooks.compute_reward(
            prev_score, prev_game_over, board_changed, self.game)

    def is_terminal(self) -> bool:
        from . import rl_hooks
        return rl_hooks.is_terminal(self.game)

    def reset_game(self) -> None:
        self.game.new_game()

    # --- layout --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="board-col"):
                yield self.board_view
                yield self.flash_bar
            with Vertical(id="side"):
                yield self.status_panel
        yield self.help_overlay
        yield Footer()

    async def on_mount(self) -> None:
        self.board_view.border_title = f"2048 · {self.game.size}×{self.game.size}"
        self.status_panel.refresh_panel()
        if self._resumed:
            self.flash_bar.set_message(
                f"[dim]resumed game — score {self.game.board.score:,}[/]"
            )
        else:
            self._show_hint()
        self._update_header()
        # 2 Hz pulse — drives the subtle highlight cycle on the win banner.
        # Cheap: a single refresh_panel() call (no BoardView redraw needed
        # because the board itself doesn't animate at idle).
        self.set_interval(0.5, self._pulse)

    # --- actions -------------------------------------------------------

    def _autosave(self) -> None:
        """Persist the current game blob inside the state file. Called
        after every successful move so a crash / Ctrl-C loses at most one
        move."""
        # Don't persist terminal game states — re-entering a game_over
        # board on relaunch is confusing. Nor won-without-continue (same
        # reason — the banner re-shows and feels stale).
        s = self.game.state()
        if s["game_over"] or (s["won"] and not s["continued"]):
            state_mod.store_savegame(self._state, None)
        else:
            state_mod.store_savegame(self._state, self.game.to_dict())
        self._state["last_size"] = self.game.size
        state_mod.save(self._state)

    def _pulse(self) -> None:
        """2 Hz idle pulse — repaints the status panel so the win/game-over
        banner can subtly alternate. BoardView is untouched at idle, so the
        cost is negligible (<0.1 ms)."""
        self.status_panel.refresh_panel(force=True)

    def _update_header(self) -> None:
        s = self.game.state()
        state_bits = []
        if s["won"] and not s["continued"]:
            state_bits.append("🏆 WON")
        elif s["won"] and s["continued"]:
            state_bits.append("continuing")
        if s["game_over"]:
            state_bits.append("GAME OVER")
        suffix = f"  ·  {', '.join(state_bits)}" if state_bits else ""
        self.sub_title = (
            f"score {s['score']:,}  ·  best {s['best']:,}  ·  "
            f"max {s['max_tile']}{suffix}"
        )
        self.board_view.border_title = f"2048 · {s['size']}×{s['size']}"

    def _show_hint(self) -> None:
        """Idle-state hint in the flash bar."""
        s = self.game.state()
        if s["game_over"]:
            self.flash_bar.set_message(
                "[red]no moves left[/] — press [bold]n[/] for a new game"
            )
        elif s["won"] and not s["continued"]:
            self.flash_bar.set_message(
                "[bold yellow]🎉 you reached 2048![/] "
                "[bold]c[/] continue · [bold]n[/] new game"
            )
        else:
            self.flash_bar.set_message(
                "[dim]slide tiles with arrows or hjkl[/]"
            )

    def _animate_move(self) -> None:
        """Kick off a short animation after a move. We simply ramp anim_t
        from 0 → 1 over ~120 ms in 4 frames. The BoardView uses anim_t to
        decide whether to show the merged-flash."""
        self.board_view.anim_t = 0.0

        def step_frame() -> None:
            t = self.board_view.anim_t + 0.25
            if t >= 1.0:
                self.board_view.anim_t = 1.0
                return
            self.board_view.anim_t = t
            # Schedule next frame.
            self.set_timer(0.03, step_frame)

        self.set_timer(0.03, step_frame)

    def action_move(self, direction: str) -> None:
        if direction not in DIRECTIONS:
            return
        if self.help_overlay.display:
            # Any key dismisses help, including movement — but we don't
            # want the first post-help keypress to also slide the board.
            self._hide_help()
            return
        merges_before = self.game.merges_count
        won_before = self.game.won
        changed = self.game.move(direction)  # type: ignore[arg-type]
        if changed:
            self._animate_move()
            state_mod.record_best(self._state, self.game.size,
                                  self.game.best_score)
            s = self.game.state()
            if s["won"] and not won_before:
                self.sounds.play("win")
            elif s["game_over"]:
                self.sounds.play("over")
            elif s["merges"] > merges_before:
                self.sounds.play("merge")
            else:
                self.sounds.play("move")
            self._autosave()
            if s["won"] and not s["continued"]:
                self.flash_bar.set_message(
                    "[bold yellow]🎉 you reached 2048![/] "
                    "[bold]c[/] continue · [bold]n[/] new"
                )
            elif s["game_over"]:
                self.flash_bar.set_message(
                    "[red]no moves left[/] — press [bold]n[/] for a new game"
                )
            else:
                last = f"merged → {s['max_tile']}" if s["merges"] else "slide"
                self.flash_bar.set_message(f"[dim]{direction}: {last}[/]")
        else:
            self.flash_bar.set_message(f"[dim]{direction}: no move[/]")
        self.status_panel.refresh_panel()
        self._update_header()

    def action_undo(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        if self.game.undo():
            self.flash_bar.set_message("[dim]↶ undo[/]")
            self.board_view.refresh()
        else:
            self.flash_bar.set_message("[red]nothing to undo[/]")
        self.status_panel.refresh_panel()
        self._update_header()

    def action_new_game(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        # Confirm if there's a substantive in-progress game we'd wipe.
        # "Substantive" = player has made moves AND the score isn't trivial.
        s = self.game.state()
        if (s["moves"] > 0 and s["score"] >= 100
                and not s["game_over"]):
            def _after(ok: bool | None) -> None:
                if ok:
                    self._do_new_game()
                else:
                    self.flash_bar.set_message("[dim]kept current game[/]")
            self.push_screen(
                ConfirmScreen(
                    f"Start a new game? "
                    f"Current score [bold]{s['score']:,}[/] will be lost."
                ),
                _after,
            )
            return
        self._do_new_game()

    def _do_new_game(self) -> None:
        self.game.new_game()
        state_mod.store_savegame(self._state, None)
        state_mod.save(self._state)
        self.board_view.refresh()
        self.status_panel.refresh_panel()
        self.flash_bar.set_message("[bold green]new game[/]")
        self._update_header()

    def action_continue_game(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        if self.game.won and not self.game.continued:
            self.game.continue_after_win()
            self.flash_bar.set_message(
                "[green]continuing past 2048 — good luck[/]"
            )
            self.status_panel.refresh_panel()
            self._update_header()
        else:
            self.flash_bar.set_message(
                "[dim]continue is for after you reach 2048[/]"
            )

    def action_change_size(self, delta: str) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        new_size = max(3, min(6, self.game.size + int(delta)))
        if new_size == self.game.size:
            self.flash_bar.set_message(
                f"[dim]already at {new_size}×{new_size}[/]"
            )
            return
        # Persist best of the OLD size first, then switch.
        state_mod.record_best(self._state, self.game.size,
                              self.game.best_score)
        self.game.set_size(new_size)
        # Load the persisted best for the NEW size.
        self.game.best_score = state_mod.best_for_size(self._state, new_size)
        self._state["last_size"] = new_size
        # Size change = new game, so clear any lingering savegame.
        state_mod.store_savegame(self._state, None)
        state_mod.save(self._state)
        self.board_view.refresh()
        self.status_panel.refresh_panel()
        self.flash_bar.set_message(
            f"[bold green]new {new_size}×{new_size} game[/]"
        )
        self._update_header()

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
        if not self.sounds.available:
            self.flash_bar.set_message(
                "[red]no audio player found[/] "
                "(install paplay / aplay / afplay)"
            )
            return
        on = self.sounds.toggle()
        self.flash_bar.set_message(
            f"[bold {'green' if on else 'yellow'}]"
            f"sound {'on' if on else 'off'}[/]"
        )

    def action_stats(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        # Refresh the state blob from disk so we show the canonical
        # best-per-size values (they're updated in-memory on every move,
        # but this is safer if a future action forgets to update).
        state_mod.record_best(self._state, self.game.size,
                              self.game.best_score)
        self.push_screen(StatsScreen(self._state))


def run(size: int = 4, *, resume: bool = True) -> None:
    app = Twenty48App(size=size, resume=resume)
    try:
        app.run()
    finally:
        # Belt-and-suspenders mouse reset (inherited discipline from
        # simcity-tui — terminal mouse tracking occasionally leaks).
        import sys
        sys.stdout.write(
            "\033[?1000l\033[?1002l\033[?1003l"
            "\033[?1006l\033[?1015l\033[?25h"
        )
        sys.stdout.flush()
