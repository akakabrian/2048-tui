# DOGFOOD — 2048-tui

_Session: 2026-04-23T10:09:37, driver: pilot, duration: 8.0 min_

**PASS** — ran for 1.5m, captured 7 snap(s), 2 milestone(s), 0 blocker(s), 1 major(s).

## Summary

Ran a rule-based exploratory session via `pilot` driver. Found **1 major(s)**, 1 UX note(s). Game state never changed during the session. Captured 2 milestone shot(s); top candidates promoted to `screenshots/candidates/`. 2 coverage note(s) — see Coverage section. 1 driver warning(s) captured — see below.

## Findings

### Blockers

_None._

### Majors
- **[M1] state appears frozen during golden-path play**
  - Collected 10 state samples; only 1 unique. Game may not be receiving keys.
  - Repro: start game → press right/up/left/down repeatedly

### Minors

_None._

### Nits

_None._

### UX (feel-better-ifs)
- **[U1] state() feedback is coarse**
  - Only 1 unique states over 14 samples (ratio 0.07). The driver interface works but reveals little per tick.

## Coverage

- Driver backend: `pilot`
- Keys pressed: 160 (unique: 12)
- State samples: 14 (unique: 1)
- Score samples: 0
- Milestones captured: 2
- Phase durations (s): A=17.2, B=25.1, C=48.1
- Snapshots: `/tmp/tui-dogfood-20260423-100745/reports/snaps/2048-tui-20260423-100807`

Unique keys exercised: ?, R, down, enter, escape, left, n, p, r, right, space, up

### Coverage notes

- **[CN1] Phase A exited early due to saturation**
  - State hash unchanged for 10 consecutive samples after 9 golden-path loop(s); no further learning expected.
- **[CN2] Phase B exited early due to saturation**
  - State hash unchanged for 10 consecutive samples during the stress probe; remaining keys skipped.

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.8 | 5340.9 | `2048-tui-20260423-100807/milestones/first_input.svg` | key=right |
| high_density | 9.9 | 5340.9 | `2048-tui-20260423-100807/milestones/high_density.svg` | interest=5340.9 |

## Driver warnings

Captured 1 non-fatal driver warning(s) during the run:

```
PilotDriver teardown: OSError: [Errno 30] Read-only file system: '/home/brian/.local/share/2048-tui/state.tmp'
d/.venv/lib/python3.12/site-packages/textual/message_pump.py", line 727, in _dispatch_message
    await self.on_event(message)
  File "/home/brian/AI/projects/tui-dogfood/.venv/lib/python3.12/site-packages/textual/app.py", line 4105, in on_event
    if not await self._check_bindings(event.key, priority=True):
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/brian/AI/projects/tui-dogfood/.venv/lib/python3.12/site-packages/textual/app.py", line 3955, in _check_bindings
    if await self.run_action(binding.action, namespace):
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/brian/AI/projects/tui-dogfood/.venv/lib/python3.12/site-packages/textual/app.py", line 4215, in run_action
    return await self._dispatch_action(action_target, action_name, params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/brian/AI/projects/tui-dogfood/.venv/lib/python3.12/site-packages/textual/app.py", line 4248, in _dispatch_action
    await invoke(public_method, *params)
  File "/home/brian/AI/projects/tui-dogfood/.venv/lib/python3.12/site-packages/textual/_callback.py", line 96, in invoke
    return await _invoke(callback, *params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/brian/AI/projects/tui-dogfood/.venv/lib/python3.12/site-packages/textual/_callback.py", line 56, in _invoke
    result = callback(*params[:parameter_count])
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/brian/AI/projects/tui-games/2048-tui/twenty48_tui/app.py", line 422, in action_move
    self._autosave()
  File "/home/brian/AI/projects/tui-games/2048-tui/twenty48_tui/app.py", line 340, in _autosave
    state_mod.save(self._state)
  File "/home/brian/AI/projects/tui-games/2048-tui/twenty48_tui/state.py", line 66, in save
    with open(tmp, "w", encoding="utf-8") as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
OSError: [Errno 30] Read-only file system: '/home/brian/.local/share/2048-tui/state.tmp'
```
