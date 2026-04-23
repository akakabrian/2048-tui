"""Persistence — best score, last-played board size, optional savegame.

Stored in `$XDG_DATA_HOME/2048-tui/state.json` (falls back to
`~/.local/share/2048-tui/`). Schema:

    {
      "best_per_size": {"3": 1234, "4": 23456, "5": 42000, "6": 50000},
      "last_size": 4,
      "continue": {...game.to_dict()...}   # optional; current game if saved
    }

Keyed-per-size best scores because 6x6 ≫ 3x3 on any sensible difficulty
curve; collapsing them would bias the leaderboard toward bigger boards
(see DECISIONS.md).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    """XDG data directory for the app. Honoured env var, falls back to
    ~/.local/share."""
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "2048-tui"
    return Path.home() / ".local" / "share" / "2048-tui"


STATE_PATH = _data_dir() / "state.json"


def load() -> dict[str, Any]:
    """Read the state blob. Returns an empty-ish default dict if missing
    or corrupt — we never crash the game over a bad save file."""
    if not STATE_PATH.exists():
        return {"best_per_size": {}, "last_size": 4}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # Back the bad file up so the player doesn't lose their history
        # silently — we rename rather than overwrite.
        try:
            STATE_PATH.rename(STATE_PATH.with_suffix(".corrupt.json"))
        except OSError:
            pass
        return {"best_per_size": {}, "last_size": 4}
    # Back-compat: early schema had a single "best" int. Migrate.
    if "best" in data and "best_per_size" not in data:
        data["best_per_size"] = {"4": int(data.pop("best", 0))}
    data.setdefault("best_per_size", {})
    data.setdefault("last_size", 4)
    return data


def save(data: dict[str, Any]) -> bool:
    """Atomic write — write to .tmp, then rename.

    Returns True on success, False on write failure. Persistence errors
    should never crash gameplay; callers may choose to surface a non-fatal
    warning when this returns False.
    """
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(STATE_PATH)
        return True
    except OSError:
        return False


def best_for_size(data: dict[str, Any], size: int) -> int:
    return int(data.get("best_per_size", {}).get(str(size), 0))


def record_best(data: dict[str, Any], size: int, score: int) -> bool:
    """Update the best score for a size if beaten. Returns True if this
    is a new record."""
    key = str(size)
    cur = int(data.get("best_per_size", {}).get(key, 0))
    if score > cur:
        data.setdefault("best_per_size", {})[key] = score
        return True
    return False


def store_savegame(data: dict[str, Any], game_blob: dict[str, Any] | None) -> None:
    """Write or clear the in-progress savegame inside the state dict.
    `game_blob` is the output of `Game.to_dict()` or None to clear."""
    if game_blob is None:
        data.pop("savegame", None)
    else:
        data["savegame"] = game_blob


def load_savegame(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the in-progress savegame blob if present — caller passes to
    `Game.from_dict`. None means "no save" (fresh start)."""
    blob = data.get("savegame")
    return blob if isinstance(blob, dict) else None


def all_best_scores(data: dict[str, Any]) -> dict[int, int]:
    """All per-size best scores as an {int size: int score} mapping.
    Guarantees keys 3..6 are present (filled with 0 if missing) so the
    stats screen can render a stable table."""
    raw = data.get("best_per_size", {}) or {}
    out: dict[int, int] = {n: 0 for n in (3, 4, 5, 6)}
    for k, v in raw.items():
        try:
            out[int(k)] = int(v)
        except (ValueError, TypeError):
            continue
    return out
