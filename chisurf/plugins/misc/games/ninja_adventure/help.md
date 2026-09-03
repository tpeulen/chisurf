# Ninja Adventure

The ported Ninja Adventure map, playable in a dockable canvas: walk the
village, talk to its people, and wander a small world that runs beside the
analysis instead of instead of it.

Like the other games it is gated behind the demo-plugins switch — it ships
with the application but stays out of the default menu until demo plugins are
enabled, because a tile-map game is not why someone opens a fitting program.

## What this window is

A dockable container (`NinjaAdventureWidget`) hosting the game canvas. The
game itself lives in `game.py` beside the tool; the window's job is only to
give it a place, keep the keyboard routing honest, and remember where it was
between sessions (window state persists through the shared plugin-state
helper).

## Controls

- **Arrow keys** — move.
- **Space / Return** — interact with what is in front of you.
- **Escape** — hand the keyboard back to the application.

The canvas takes the keyboard only while it has focus.

## Where things live

- `game.py` — the ported map and its behaviour.
- `data/` — the game's assets.
- `test/` — the physics and interaction tests, including the hitch-step check
  that nothing walks through a wall.

Press **Guide** for the walk-through.
