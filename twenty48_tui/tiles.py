"""Tile palette — one style per value, matching Cirulli's browser colours
then darkened slightly for terminal legibility.

The classic palette (tailored for light backgrounds in the browser) reads
as pastel on a dark terminal. We rebalance:
  * low tiles (2–8) stay cool / cream on a warm brown background
  * mid tiles (16–128) pick up orange/amber saturation
  * high tiles (256–2048) go gold/yellow (the target colour)
  * past-win tiles (4096+) fade to blue/black — they're bragging rights,
    not the primary goal
"""

from __future__ import annotations

from rich.style import Style

# Per-value (fg, bg) colours. We parse into Style objects once at import
# time — Style.parse() is non-trivial and tile rendering hits this every
# frame. Same perf discipline as simcity-tui.
_PALETTE: dict[int, tuple[str, str]] = {
    0:    ("rgb(100,90,78)",   "rgb(30,26,22)"),    # empty cell
    2:    ("rgb(120,110,100)", "rgb(240,230,210)"),
    4:    ("rgb(90,80,70)",    "rgb(235,220,190)"),
    8:    ("rgb(255,250,240)", "rgb(240,150,90)"),
    16:   ("rgb(255,250,240)", "rgb(240,125,70)"),
    32:   ("rgb(255,250,240)", "rgb(240,100,70)"),
    64:   ("rgb(255,250,240)", "rgb(240,75,55)"),
    128:  ("rgb(255,250,240)", "rgb(230,195,95)"),
    256:  ("rgb(255,250,240)", "rgb(230,185,75)"),
    512:  ("rgb(255,250,240)", "rgb(230,175,55)"),
    1024: ("rgb(255,250,240)", "rgb(230,165,35)"),
    2048: ("rgb(255,250,240)", "rgb(230,155,15)"),
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


# Unknown / out-of-palette safety net — loud magenta so a regression is
# obvious instead of a silent KeyError during render.
UNKNOWN_STYLE = Style.parse("bold rgb(255,0,255) on black")


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
