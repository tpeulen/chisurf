---
type: Guide
title: 'Games: a break between fits'
description: 'Tool: Tools → System → Games (games), a hub that hosts the five games number_quest, minesweeper, tetris, pong and breakout.'
tags: [guides, games]
---

# Games: a break between fits

**Tool:** *Tools → System → Games* (`games`), a hub that hosts the five games `number_quest`, `minesweeper`,
`tetris`, `pong` and `breakout`. Each game is built from the physics and statistics of fluorescence (a lifetime
dial, a hot-pixel field, a spectral wall of bricks), but nothing here analyses data.

## 1. The window

```{figure} figures/games_breakout.png
:name: fig-games-breakout
:width: 100%

The hub with Breakout in play: the game list on the left, the header with the keys of the selected game, the game
filling the rest.
```

The list on the left selects the game (its description is the tooltip). The header repeats the description and the
keys. Every game is built the first time it is selected and kept alive while you visit another, so a round survives
a look at the list. Click into the game area before typing: the keys go to the game that is shown, press and release.

## 2. Keys and pointer

| Game | Keys | Pointer |
|---|---|---|
| Number Quest | Left/Right dial, Q/E steps of ten, Enter submit, R new round | click the decay plot to dial a lifetime; click the left half of the second caption to submit, the right half for a new round |
| Minesweeper | Arrows or WASD move (held keys repeat), Enter/Space scan, F flag, Q/E board size, R reset | left click scans, right click flags, click the preset name to cycle the board size |
| Tetris | Left/Right move, Down soft drop, Up rotate, Space drop, P pause, R reset | none |
| Pong | Up/Down paddle, W/S second player, P pause, M mode, R reset | drag in either half of the court to move that paddle |
| Breakout | Left/Right or A/D paddle (hold), Space or Enter launch, P pause, M mute, R reset | drag in the field to move the paddle; a stuck ball goes with it |

A key that is released stops its action; losing the window focus releases every held key, so a paddle never keeps
running after you switch windows. Sound is a switch only (the native window plays no audio); it is greyed where there
is no audio output.

## 3. Application

The games are tested with real key and pointer events through the Qt window that hosts them
(`chisurf/plugins/misc/games/test/test_games_real_input.py`): the paddle, piece, cursor and dial must actually move.
See also the generated reference pages for [Games](../reference/plugins/games.md) and
[Breakout](../reference/plugins/breakout.md).
