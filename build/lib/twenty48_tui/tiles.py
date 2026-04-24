"""Tile palette — one style per value, tuned for the polished dark TUI.

The ramp follows the mockup's intent:
  * 2/4 are cream and peach
  * 8–64 climb through orange into red-orange
  * 128 is the red peak
  * 256–2048 shift into yellow, warm gold, and trophy gold
"""

from __future__ import annotations

from rich.style import Style

# Per-value (fg, bg) colours. We parse into Style objects once at import
# time — Style.parse() is non-trivial and tile rendering hits this every
# frame. Same perf discipline as simcity-tui.
_PALETTE: dict[int, tuple[str, str]] = {
    0:    ("rgb(100,90,78)",   "rgb(34,31,27)"),    # empty cell
    2:    ("rgb(58,48,37)",    "rgb(246,225,188)"),
    4:    ("rgb(60,47,33)",    "rgb(238,199,139)"),
    8:    ("rgb(255,245,218)", "rgb(236,150,47)"),
    16:   ("rgb(255,242,216)", "rgb(229,118,39)"),
    32:   ("rgb(255,238,212)", "rgb(219,83,34)"),
    64:   ("rgb(255,235,211)", "rgb(206,58,36)"),
    128:  ("rgb(255,232,210)", "rgb(177,48,43)"),
    256:  ("rgb(48,38,19)",    "rgb(249,200,50)"),
    512:  ("rgb(43,34,16)",    "rgb(245,179,28)"),
    1024: ("rgb(38,29,12)",    "rgb(228,142,12)"),
    2048: ("rgb(30,22,8)",     "rgb(255,211,38)"),
    # Beyond 2048 — cool blue/violet so they read as "past the finish line".
    4096: ("rgb(255,250,240)", "rgb(60,90,160)"),
    8192: ("rgb(255,250,240)", "rgb(80,70,170)"),
}

# Anything above 8192 gets the deepest style — you're in the Knuth zone.
_OVER_MAX = ("rgb(255,250,240)", "rgb(20,20,40)")

# Pre-parsed styles. Plain (regular) + `bold` variant used by the "just
# merged" animation flash.
STYLES: dict[int, Style] = {}
STYLES_BOLD: dict[int, Style] = {}

for v, (fg, bg) in _PALETTE.items():
    STYLES[v] = Style.parse(f"bold {fg} on {bg}")
    STYLES_BOLD[v] = Style.parse(f"bold {fg} on {bg} reverse")


def style_for(value: int, *, flash: bool = False) -> Style:
    """Style for a tile. `flash` inverts fg/bg for a frame — used right
    after a merge so the new tile reads as 'just merged'."""
    if value in STYLES:
        return STYLES_BOLD[value] if flash else STYLES[value]
    # Fallback for values above the palette — dark background, bright fg.
    fg, bg = _OVER_MAX
    return Style.parse(f"bold {fg} on {bg}" + (" reverse" if flash else ""))


def cell_text(value: int) -> str:
    """Render a tile value into a short centered string for a 6-cell wide
    box (the default tile box width). Empty cells render as 6 spaces so
    the grid stays aligned."""
    if value == 0:
        return "      "
    s = str(value)
    # Pad/truncate to 6. Values up to 131072 fit; beyond that we truncate.
    if len(s) > 6:
        s = s[-6:]
    return s.center(6)
