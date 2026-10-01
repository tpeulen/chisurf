# Tetris Game Plugin

Spectral Tetris is available through the retained Qt widget and the standalone
EMTK factory `chisurf.plugins.misc.games.tetris.app:make_app`. The native factory
imports no Qt bindings, GUI host or chigame GPU package.

The two views share `TetrisModel`: a 10 × 22 well, seven tetrominoes, the original
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
The Qt widget retains its existing sound control. No platform-only audio
dependencies were added. Neither current view has a next-piece preview; older
metadata described one that the current rules and reference do not contain.

Verification:

- `python -m pytest chisurf/plugins/misc/games/tetris/test -q`
- `python -m chisurf.plugins.misc.games.tetris.test.capture_qt`
- `python -m chisurf.plugins.misc.games.tetris.test.capture_native`

Capture commands require a working GPU adapter. Genuine populated Qt and native
normal/narrow screenshots are in `test/renders/`, alongside the visual verdict
(95/100). Native renders include populated, paused and game-over states.
