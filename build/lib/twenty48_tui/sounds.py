"""Optional synth sounds for 2048-tui — short blips on merge / win / over.

Off by default because most players run 2048 in a shared terminal / tmux
and a click for every merge gets annoying fast. Toggled with `s` at
runtime or `TWENTY48_SOUND=1` in the environment.

Implementation follows the tui-game-build skill's sound recipe:

* stdlib `wave` module synthesises small sine-wave .wav files at first use
  and caches them in the user's XDG runtime dir
* playback via `paplay` / `aplay` / `afplay`, whichever is first on PATH;
  fire-and-forget `subprocess.Popen(..., start_new_session=True)` so we
  don't block the UI
* per-sound debounce (120 ms) so holding an arrow key and triggering
  back-to-back merges doesn't spawn 20 parallel paplay subprocesses

If no player is on PATH we silently disable — never crash the game over
audio.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import time
import wave
from pathlib import Path
from typing import Callable


# ---- runtime config --------------------------------------------------

_PLAYER: str | None = None
for _cmd in ("paplay", "aplay", "afplay"):
    if shutil.which(_cmd):
        _PLAYER = _cmd
        break


def _runtime_dir() -> Path:
    """Where to cache the synthesised .wav files."""
    base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR") or "/tmp"
    d = Path(base) / "2048-tui-sounds"
    d.mkdir(parents=True, exist_ok=True)
    return d


# (freq_hz, duration_s, amplitude)
_TONES: dict[str, tuple[float, float, float]] = {
    # Move is a short dim tick so it doesn't dominate a rapid series
    "move":  (520.0, 0.030, 0.18),
    # Merge is a warmer, longer tone — rewards the player
    "merge": (720.0, 0.070, 0.30),
    # Win is a higher triumphant pip (longer)
    "win":   (1040.0, 0.180, 0.35),
    # Game over is a low thud
    "over":  (180.0, 0.250, 0.30),
}


def _synthesise(path: Path, freq: float, dur: float, amp: float) -> None:
    """Write a mono 16-bit PCM WAV of a quick sine blip with a soft
    attack/decay envelope (a raw square tone clicks audibly)."""
    sr = 22_050
    n = int(sr * dur)
    # 10 ms attack/release, rest sustain. Prevents click artefacts at the
    # start and end of the sample.
    attack = int(sr * 0.010)
    release = int(sr * 0.010)
    frames = bytearray()
    for i in range(n):
        env = 1.0
        if i < attack:
            env = i / max(1, attack)
        elif i > n - release:
            env = max(0.0, (n - i) / max(1, release))
        sample = amp * env * math.sin(2 * math.pi * freq * i / sr)
        frames += struct.pack("<h", int(sample * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))


def _ensure_wav(name: str) -> Path | None:
    """Idempotently synthesise and return the path to a named sample."""
    if name not in _TONES:
        return None
    path = _runtime_dir() / f"{name}.wav"
    if not path.exists() or path.stat().st_size < 1000:
        freq, dur, amp = _TONES[name]
        try:
            _synthesise(path, freq, dur, amp)
        except OSError:
            return None
    return path


class Sounds:
    """Instance state (enabled / last-played timestamps) so the app can
    own one and toggle it. Sub-200 byte footprint; no threads involved."""

    def __init__(self, enabled: bool | None = None) -> None:
        # Default enabled iff the env var is set — never auto-enable
        # for a player who didn't opt in.
        if enabled is None:
            enabled = os.environ.get("TWENTY48_SOUND", "").lower() in ("1", "true", "yes")
        self.enabled = bool(enabled) and _PLAYER is not None
        self._last_played: dict[str, float] = {}
        # Debounce window — consecutive play() for the same sound inside
        # this window becomes a no-op.
        self._debounce_s = 0.120
        # Hook for tests — if set, called instead of spawning a subprocess.
        self._test_hook: Callable[[str, Path], None] | None = None

    @property
    def available(self) -> bool:
        """Is there a system audio player at all?"""
        return _PLAYER is not None

    def toggle(self) -> bool:
        """Flip the enabled flag. Returns the new value. If no player was
        detected, force stays off and we return False."""
        if _PLAYER is None:
            self.enabled = False
            return False
        self.enabled = not self.enabled
        return self.enabled

    def play(self, name: str) -> None:
        """Fire-and-forget play. Silent no-op if disabled, unknown, or
        debounced. Never raises."""
        if not self.enabled:
            return
        now = time.monotonic()
        last = self._last_played.get(name, 0.0)
        if now - last < self._debounce_s:
            return
        self._last_played[name] = now
        path = _ensure_wav(name)
        if path is None:
            return
        if self._test_hook is not None:
            try:
                self._test_hook(name, path)
            except Exception:
                pass
            return
        if _PLAYER is None:
            return
        try:
            subprocess.Popen(
                [_PLAYER, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, ValueError):
            # Lost the player since startup — quietly disable.
            self.enabled = False
