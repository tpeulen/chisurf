---
type: Guide
title: 'Games: a break between fits'
description: 'Tool: Tools → System → Games (games), a hub that hosts the five games number_quest, minesweeper, tetris, pong and breakout.'
tags: [guides, games]
---

# Games: a break between fits

**Tool:** *Tools → System → Games* (`games`), a hub that hosts the five games `number_quest`, `minesweeper`,
`tetris`, `pong` and `breakout`. Each game is built from the physics and statistics of fluorescence (a lifetime
dial, a hot-pixel field, a spectral wall of bricks), but nothing here analyses data. See [Games and generated round data](../concepts/games.md)
for the interpretation of the lifetime curve and the limits of these displays.

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

Standalone defaults remain Breakout 820×690, Pong 820×640, Tetris 520×620,
Minesweeper 560×620 and Number Quest 560×420; the launcher starts at 1200×800.
Resizing a standalone window keeps that size when it reopens. A first launch
starts with the game defaults; an existing saved round is restored when available.

### Help, Restart and Guide

Each game has a shared **Help / Restart / Guide** row beside its existing Sound
control. The game canvas, scores and any pause behavior remain below it.

1. Select a game. It supplies its own playable round; no measurement file or
   generated-data import is needed.
2. Open **Guide**. The tour leaves the round unchanged and points at **Restart**.
   Press Restart yourself when ready to replace the current round; the tour
   waits for that action.
3. Follow the next step to **Help** and press it. The help page explains that
   game's real controls, rules and sound behavior. Close the help page to return
   to the tour and game.

4. Advance to the final step and press **Restart** again. Check the fresh round,
   then finish the tour and try the keys below in the game area.

Restart uses the game's existing reset behavior. Merely opening Help or Guide
does not restart the game. A help or tour overlay owns input so a click intended
for it does not also reveal a cell, submit a guess or move a paddle underneath.

```{figure} figures/games_number_quest_header.png
:name: fig-games-native-header
:width: 560px

Number Quest with the shared Help, Restart and Guide controls. Sound remains
unavailable when no audio output has been supplied; the existing lifetime dial,
hint and footer controls stay in the canvas.
```

## 2. Keys and pointer

| Game | Keys | Pointer |
|---|---|---|
| Number Quest | Left/Right dial, Q/E steps of ten, Enter/Space submit, R new round | click the decay plot to dial a lifetime; click the left half of the second caption to submit, the right half for a new round |
| Minesweeper | Arrows move (held keys repeat), Enter/Space scan, F flag, Q/E board size, R reset | left click scans, right click flags, click the preset name to cycle the board size |
| Tetris | Left/Right move, Down soft drop, Up rotate, Space drop, P pause, R reset | none |
| Pong | Up/Down paddle, W/S second player, P pause, M opponent mode, N mute, R reset | drag in either half of the court to move that paddle |
| Breakout | Left/Right paddle (hold), Space or Enter launch, P pause, M mute, R reset | drag in the field to move the paddle; a stuck ball goes with it |

A key that is released stops its action; losing the window focus releases every held key, so a paddle never keeps
running after you switch windows. Pending second-player input is cleared too.
Closing a game stops further key and pointer changes; a queued redraw remains
serviceable while a game is paused. The native games do not open an audio device by default. Sound remains greyed
where there is no audio output. If an audio output
is supplied through Python, losing focus silences it without changing the saved
sound preference, and closing releases it once.

## 3. Application

The games are tested with real key and pointer events through the Qt window that hosts them
(`chisurf/plugins/misc/games/test/test_games_real_input.py`): the paddle, piece, cursor and dial must actually move.
See also the generated reference pages for [Games](../reference/plugins/games.md) and
[Breakout](../reference/plugins/breakout.md).

## 4. Native Python entrypoint

The canonical Number Quest native app now lives in its GUI package:

```python
from chisurf.plugins.misc.games.number_quest.gui.app import make_app

app = make_app()
app.game.reset(target=53)
app.estimate = 50
app.submit()
print(app.tau, app.game.attempts_remaining)
app.close()
```

The standalone launcher is `pixi run -e test python -m chisurf.emtk --plugin number_quest`.
The richer app's controls, held/released keys, saved round and window dimensions
are retained; the former alternate native implementation is retired.
