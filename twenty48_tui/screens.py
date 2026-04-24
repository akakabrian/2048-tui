"""Modal screens — stats table, confirm-dialog.

Using `ModalScreen` rather than in-app Static overlays so the harness can
assert on a clean screen-stack (and so they dim the background the way
Textual modals do).

Per the tui-game-build skill: priority=True App bindings (our movement
arrows) beat ModalScreen bindings. We stick to non-conflicting keys
(`n`, `y`, `escape`, `q`) inside modals.

Textual 8+ warning: `Static(rich_text_object, id=...)` can crash the
compositor mid-render. Pass a markup string to `super().__init__` and
rely on markup for inline styling instead of building a `rich.Text`.
"""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from .engine import Game
from . import state as state_mod


class StatsScreen(ModalScreen[None]):
    """Per-size best scores + lifetime aggregate. Dismiss with any key."""

    BINDINGS = [
        Binding("escape", "dismiss", "close"),
        Binding("q", "dismiss", "close"),
        Binding("enter", "dismiss", "close"),
        Binding("space", "dismiss", "close"),
    ]

    def __init__(self, state: dict) -> None:
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        with Vertical(id="stats-body"):
            yield Static(self._build_markup(), id="stats-content")
            yield Static(
                "[dim]press any key to close[/]",
                id="stats-dismiss",
            )

    def _build_markup(self) -> str:
        """Build a Rich markup string (not a Text object — Textual 8+
        sometimes chokes on Text passed into Static constructors)."""
        best = state_mod.all_best_scores(self._state)
        last = self._state.get("last_size")
        lines: list[str] = []
        lines.append("[bold rgb(240,200,100)]STATISTICS[/]")
        lines.append("")
        lines.append("Best scores by size:")
        lines.append("")
        for size in (3, 4, 5, 6):
            v = best[size]
            bar = "█" * min(20, v // 500) if v else ""
            marker = "  [dim]current[/]" if last == size else ""
            lines.append(
                f"  [bold]{size}×{size}[/]  "
                f"[rgb(230,155,15)]{v:>8,}[/]  "
                f"[rgb(230,155,15)]{bar}[/]{marker}"
            )
        total = sum(best.values())
        lines.append("")
        lines.append(f"  [bold]total[/]  [bold]{total:>8,}[/]")
        lines.append("")
        lines.append("[dim]best scores persist across sessions in[/]")
        lines.append(f"[dim]{state_mod.STATE_PATH}[/]")
        return "\n".join(lines)

    # Any key dismisses — on_key catches what bindings don't.
    def on_key(self, event: events.Key) -> None:
        # Prevent dismiss keys from bubbling into app-level actions
        # (for example `n` triggering "new game" right after closing stats).
        event.stop()
        event.prevent_default()
        self.dismiss(None)


class RulesScreen(ModalScreen[None]):
    """Rules modal for 2048."""

    BINDINGS = [Binding("escape", "dismiss", show=False),
                Binding("q", "dismiss", show=False),
                Binding("r", "dismiss", show=False)]

    DEFAULT_CSS = """
    RulesScreen {
        align: center middle;
        background: #07190f 70%;
    }
    #rules-box {
        width: 80%;
        max-width: 88;
        height: auto;
        max-height: 90%;
        border: round #ffd45a;
        background: #07190f;
        padding: 1 2;
    }
    #rules-title {
        color: #ffd45a;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }
    #rules-body {
        color: #efe8d1;
    }
    #rules-foot {
        margin-top: 1;
        color: #8faa83;
        text-align: center;
    }
    """

    def __init__(self, variant: str, text: str) -> None:
        super().__init__()
        self._variant = variant
        self._text = text

    def compose(self) -> ComposeResult:
        with Vertical(id="rules-box"):
            yield Static(f"◆ {self._variant} — rules ◆", id="rules-title")
            with VerticalScroll():
                yield Static(self._text, id="rules-body")
            yield Static("[dim]Esc / r / q — close[/dim]", id="rules-foot")


class ConfirmScreen(ModalScreen[bool]):
    """Generic yes/no confirm — used when starting a new game would discard
    an in-progress game with a good score."""

    BINDINGS = [
        Binding("y", "confirm_yes", "yes"),
        Binding("n", "confirm_no", "no"),
        Binding("escape", "confirm_no", "cancel"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-body"):
            yield Static(self._message, id="confirm-msg")
            yield Static("[bold]y[/]es / [bold]n[/]o", id="confirm-keys")

    # Separate actions for yes/no — Textual's action-argument parsing for
    # `confirm(True)` vs `confirm(False)` is version-sensitive (6.x returns
    # strings, 8.x returns Python literals). Splitting the actions makes
    # this immune to that shift.
    def action_confirm_yes(self) -> None:
        self.dismiss(True)

    def action_confirm_no(self) -> None:
        self.dismiss(False)


class EndScreen(ModalScreen[str]):
    """Win / game-over celebration card."""

    BINDINGS = [
        Binding("escape", "dismiss_screen('dismiss')", show=False),
        Binding("enter", "dismiss_screen('new')", show=False),
        Binding("n", "dismiss_screen('new')", show=False),
        Binding("c", "dismiss_screen('continue')", show=False),
    ]

    DEFAULT_CSS = """
    EndScreen {
        align: center middle;
        background: #07190f 70%;
    }
    #end-box {
        width: 60;
        height: auto;
        border: heavy #ffd45a;
        background: #07190f;
        padding: 1 3;
    }
    #end-banner {
        text-align: center;
        color: #ffd45a;
        text-style: bold;
    }
    #end-body {
        text-align: center;
        color: #efe8d1;
        margin-top: 1;
    }
    #end-stats {
        text-align: center;
        color: #8faa83;
        margin-top: 1;
    }
    #end-foot {
        text-align: center;
        color: #8faa83;
        margin-top: 1;
    }
    """

    def __init__(self, game: Game, elapsed: str, won: bool) -> None:
        super().__init__()
        self._game = game
        self._elapsed = elapsed
        self._won = won

    def compose(self) -> ComposeResult:
        if self._won:
            title = " Y O U   R E A C H E D   2 0 4 8 "
            body = "✦   ✦   ✦   ✦   ✦   ✦   ✦   ✦"
            prompt = "[dim]Enter / n — play again   ·   c — continue   ·   Esc — dismiss[/dim]"
        else:
            title = " G A M E   O V E R "
            body = "•   •   •   •   •   •   •   •"
            prompt = "[dim]Enter / n — play again   ·   Esc — dismiss[/dim]"
        banner = "\n".join(
            [
                " ✦   ✦   ✦   ✦   ✦   ✦   ✦   ✦ ",
                " ╔══════════════════════════╗ ",
                f" ║{title.center(26)}║ ",
                " ╚══════════════════════════╝ ",
                " ✦   ✦   ✦   ✦   ✦   ✦   ✦   ✦ ",
            ]
        )
        s = self._game.state()
        stats = (
            f"[b]2048 {s['size']}x{s['size']}[/b]\n"
            f"Time:   {self._elapsed or '00:00'}\n"
            f"Moves:  {s['moves']}\n"
            f"Score:  {s['score']:,}\n"
            f"Max:    {s['max_tile']}\n"
            f"Seed:   {self._game.seed if self._game.seed is not None else '—'}"
        )
        with Vertical(id="end-box"):
            yield Static(banner, id="end-banner")
            yield Static(body, id="end-body")
            yield Static(stats, id="end-stats")
            yield Static(prompt, id="end-foot")

    def action_dismiss_screen(self, result: str) -> None:
        if result == "continue" and not self._won:
            self.dismiss("dismiss")
            return
        self.dismiss(result)
