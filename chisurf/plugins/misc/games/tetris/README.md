# Tetris Game Plugin

Spectral Tetris is the standalone EMTK factory
`chisurf.plugins.misc.games.tetris.app:make_app`. It imports no Qt bindings,
GUI host or chigame GPU package.

The view drives `TetrisModel`: a 10 × 22 well, seven tetrominoes, the original
rotation and collision rules, delayed direction repeat, line scoring and faster
falling every ten cleared lines. The model has no GUI or GPU imports.

Controls:

- Left/Right or A/D: move.
- Up or W: rotate; after game over, restart.
- Down or S: soft drop.
- Space: hard drop.
- P: pause/resume.
- R: restart.

The native surface releases held keys on focus loss and stops animation on close.
Saved settings restore the well, falling piece, fall timer, score, lines, level,
pause and game-over flags atomically. Malformed saved rounds leave the live round
unchanged. Keyboard holds are not saved.

Labels and tooltips are localized in English, German, French, Spanish,
Portuguese and Russian. The well, count panel, pause/game-over overlays and
control captions fit normal and narrow windows. The game-over overlay can also
be clicked to restart.

EMTK currently provides no audio backend. Native music and sound effects are
unavailable and its Sound control is disabled with a localized explanation.
No platform-only audio dependencies were added. There is no next-piece
preview; older metadata described one that the current rules do not contain.

Verification:

- `python -m pytest chisurf/plugins/misc/games/tetris/test -q`
- `python -m chisurf.plugins.misc.games.tetris.test.capture_native`

Capture commands require a working GPU adapter. Native normal/narrow
screenshots of populated, paused and game-over states are in `test/renders/`.
