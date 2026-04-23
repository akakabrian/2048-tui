# 2048-tui
Chase the tile. Chase the dream.

![Hero](screenshots/hero.svg)
![Gameplay](screenshots/gameplay.svg)
![End screen](screenshots/endscreen.svg)

## About
Slide up. Slide left. Slide down. Watch twos turn to fours turn to eights turn to an incomprehensible sixteen-thousand. Configurable board sizes, undo, autosave, live stats modal, a tiny synth sound stack, mouse + keyboard. The number that ate a generation.

## Screenshots
![Hero](screenshots/hero.svg)
![Gameplay](screenshots/gameplay.svg)
![End screen](screenshots/endscreen.svg)

## Install & Run
```bash
git clone https://github.com/akakabrian/2048-tui
cd 2048-tui
make
make run
```

## Controls
<Add controls info from code or existing README>

## Testing
```bash
make test       # QA harness
make playtest   # scripted critical-path run
make perf       # performance baseline
```

## License
MIT

## Built with
- [Textual](https://textual.textualize.io/) — the TUI framework
- [tui-game-build](https://github.com/akakabrian/tui-foundry) — shared build process
