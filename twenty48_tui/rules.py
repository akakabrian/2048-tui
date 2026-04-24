"""Rules text for 2048-tui."""

RULES_TEXT = '''
2048
====

Slide numbered tiles to combine them and reach 2048.

Object
------
Create a tile with the value 2048 by sliding and merging matching tiles.

Rules
-----
Use arrow keys to slide all tiles in one direction. Every tile slides
as far as it can. When two tiles with the same number collide, they
merge into one tile with their combined value.

A new random tile (2 or 4) appears after each move.

The game is won the first time a 2048 tile is created — but play
continues for higher scores.

The game is lost when the board is full and no merges are possible.

Controls summary
----------------
Move:   ← → ↑ ↓
Undo:   u
New:    n
Help:   ?
Rules:  r
Music:  m (toggle)
Quit:   q
'''
