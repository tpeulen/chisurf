# Minesweeper

Standalone native EMTK:

```sh
python -m emtk.native --app chisurf.plugins.misc.games.minesweeper.gui.app:make_app
```

Arrows/WASD move the cursor. Enter/Space reveals, F toggles a flag, R restarts,
and Q/E cycle the three board presets. Left click reveals a cell; right click
toggles its flag. Click the preset label to cycle the board, the first help
line to scan, or the second to restart. Controls include translated tooltips.
All displayed strings support English, German, French, Spanish, Portuguese
and Russian; changing locale preserves the round.

`export_settings()` and `restore_settings()` preserve the full round, including
mines, revealed cells, flags, terminal status, cursor and selected difficulty.
The existing Qt widget remains available through its original entrypoint.

Native sound playback is an explicit parity gap: EMTK has no audio adapter,
while the original mixer requires QtMultimedia. Sound starts off and the
control is disabled until a host supplies `audio_callback` to `MinesweeperApp`.
The callback receives `(event, value)` for sound enablement, reveals (620 Hz)
and flags (480 Hz); the sound preference is included in saved state. A shared
native music/effects adapter is needed for original soundtrack parity.

`gui/glyphs.json` contains the original ASCII glyph art from
`chisurf/gui/chigame/pixelfont.py`; Unicode uses EMTK's font renderer. The asset
is local because the legacy chigame package initializer imports Qt. Moving
that face to a shared Qt-free asset module would remove this local copy.

Screenshots are in `test/renders`. The original Qt widget capture was obtained
before port edits; the offscreen widget grab cannot include its embedded GPU
canvas, so comparison uses the real legacy game's GPU-rendered frame captured
under QApplication. Reproduce populated comparisons with:

```sh
QT_QPA_PLATFORM=offscreen python -m chisurf.plugins.misc.games.minesweeper.test.capture_native --qt
```
