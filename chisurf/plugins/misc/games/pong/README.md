# Pong

Pong has a native EMTK view and the existing Qt/chigame view. Both use
`model.py` for CPU tracking, paddle/wall collisions, spectral transfers,
scoring, the one-second serve countdown, and the first-to-seven winner.

Run the native view with:

```sh
python -m chisurf.emtk --plugin pong
```

Up/Down moves the left paddle. M switches between CPU and two-player mode;
W/S moves the right paddle in two-player mode. P pauses, R resets, N toggles
mute, and Enter/Space restarts after a win. The native view also supports
mouse dragging on either paddle's half of the field, and clickable footer
controls with tooltips. Narrow windows fit the whole field without losing a
paddle. Text and tooltips cover English, German, French, Spanish, Portuguese,
and Russian.

The native app exports/restores the active round, including scores, paddle
positions, the ball, serve countdown, mode, pause, mute and winner. It releases
held inputs on key-up/focus loss and stops animation when closed. Transient
impact sparks are regenerated during play rather than persisted.

The current EMTK toolkit has no shared native audio backend. The native view
preserves the sound preference and mute state, and accepts an injected audio
adapter, but the default factory does not play music or effects. The Qt view
retains its original audio playback.

Verification:

```sh
QT_QPA_PLATFORM=offscreen python -m pytest chisurf/plugins/misc/games/pong/test -q
python -m ruff check chisurf/plugins/misc/games/pong
python -m chisurf.plugins.misc.games.pong.test.capture_native
QT_QPA_PLATFORM=offscreen python -m chisurf.plugins.misc.games.pong.test.capture_qt
```

`test/renders` contains the genuine Qt widget and legacy GPU reference plus
native normal/narrow serve, rally, paused and winner captures. The visual
verdict improved from 88 to 94 after measuring the original footer spacing.
GPU captures need access to the platform graphics adapter.
