---
type: Concept
title: Games and generated round data
description: How the native games use generated round state and fluorescence-themed displays without analysing experimental data.
tags: [concepts, games]
---

# Games and generated round data

The five native games are recreational tools with fluorescence-themed displays.
They generate their own boards, pieces, balls or hidden targets. They do not load
an experimental dataset, fit a model to observations, estimate measurement
uncertainty or create an analysis result. The [Games workflow](../guides/95_games.md)
shows the shared Help, Restart and Guide controls and the keys for each game.

## The lifetime dial

Number Quest chooses a hidden integer between 1 and 100. The player's current
integer estimate, $n$, is displayed as a lifetime $\tau = 0.1n$ ns. Its curve is
constructed from the normalized exponential

$$
I(t) = \exp(-t/\tau),
$$

sampled over a fixed interval from 0 to 10 ns. Changing the estimate changes this
constructed curve; previous guesses can also be shown. The higher/lower hint
comes from comparing the guess with the hidden target. It is not a residual or
an estimate from photon arrival times. The game has no instrument response,
background model, photon noise or goodness-of-fit calculation.

For measured decays, see [TCSPC lifetime analysis](tcspc_lifetime.md). A smooth
curve and a displayed value in ns alone do not establish a measured lifetime.

## Other game displays

- Minesweeper's adjacent counts describe mines on its generated board. They do
  not identify hot pixels or classify detector data.
- Tetris uses falling pieces and completed rows. Its spectral colours and score
  express game progress rather than recovered spectral components.
- Pong's court, rally and wavelength cues are game state. A score is not a
  transfer efficiency or a photon count.
- Breakout's brick health, colour, score and remaining lives define its challenge.
  They are not calibrated intensity, bleaching or lifetime measurements.

## Round state, controls and sound

Restart replaces the round using the existing game rules. Help explains the
controls; Guide points at Restart, Help and a final Restart to check the fresh round. It
waits for the player to press each control. Opening a guide does not generate another round automatically.
Games already provide their own playable state, so these tours need no external
input or separate demo data layer.

The native host can preserve a saved round and window dimensions. Switching
between games in the Games window retains the existing game instances; losing
focus releases held controls. These saved rounds are application preferences,
not scientific provenance or analysis datasets.

No audio device is opened by default. A supplied audio output is optional, and
Sound remains unavailable where none is present. Sound is one shared toggle in
all five games, drawn like the Help, Restart and Guide buttons beside it: pressed
with 🔊 while on, 🔇 while off, greyed without an audio output. Breakout has no
audio backend but keeps its Sound preference switchable, as before. The guide does not activate
playback. See the [game controls and sound behavior](../guides/95_games.md#2-keys-and-pointer)
for the per-game actions.

## Where it lives

The hub is `chisurf/plugins/misc/games/` (Number Quest, Minesweeper, Tetris, Pong, Breakout). Each game keeps its state
while another is shown and mutes its sound whenever the window is not in front; the list, the keys and the Help, Restart
and Guide controls are in the [Games workflow](../guides/95_games.md).

Tools: Number Quest (`chisurf/plugins/misc/games/number_quest/`), Minesweeper (`chisurf/plugins/misc/games/minesweeper/`), Tetris (`chisurf/plugins/misc/games/tetris/`), Pong (`chisurf/plugins/misc/games/pong/`), Breakout (`chisurf/plugins/misc/games/breakout/`).
