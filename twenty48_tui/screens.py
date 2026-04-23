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

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

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
    def on_key(self, event) -> None:
        self.dismiss(None)


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
