# Minesweeper

Standalone native EMTK:

```sh
python -m emtk.native --app chisurf.plugins.misc.games.minesweeper.gui.app:make_app
```

Arrow keys move the cursor. Enter/Space reveals, F toggles a flag, R restarts,
and Q/E cycle the three board presets. Left click reveals a cell; right click
toggles its flag. Click the preset label to cycle the board, the first help
line to scan, or the second to restart. Controls include translated tooltips.
All displayed strings support English, German, French, Spanish, Portuguese
and Russian; changing locale preserves the round.

`export_settings()` and `restore_settings()` preserve the full round, including
mines, revealed cells, flags, terminal status, cursor and selected difficulty.

EMTK has no audio adapter, so the app plays no sound of its own. Sound starts off and the
control is disabled until a host supplies `audio_callback` to `MinesweeperApp`.
The callback receives `(event, value)` for sound enablement, reveals (620 Hz)
and flags (480 Hz); the sound preference is included in saved state. A shared
native music/effects adapter would be needed for a soundtrack.

`gui/glyphs.json` contains the original ASCII glyph art from
`chisurf/gui/chigame/pixelfont.py`; Unicode uses EMTK's font renderer. The asset
is plugin-local data; a shared glyph asset module would remove this local copy.

Screenshots are in `test/renders`. Reproduce them with:

```sh
python -m chisurf.plugins.misc.games.minesweeper.test.capture_native
```
