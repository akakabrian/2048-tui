"""Entry point — `python play.py [--size N]`."""

from __future__ import annotations

import argparse

from twenty48_tui.app import run


def main() -> None:
    p = argparse.ArgumentParser(prog="2048-tui")
    p.add_argument("--size", type=int, default=4,
                   help="board size (3..6, default 4)")
    args = p.parse_args()
    if not 3 <= args.size <= 6:
        p.error("size must be in 3..6")
    run(size=args.size)


if __name__ == "__main__":
    main()
