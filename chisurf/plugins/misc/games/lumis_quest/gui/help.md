# Lumis Quest

The overworld game on the chigame engine: a character walks a tile map, talks
to NPCs, and picks up quests. It runs in a dockable canvas inside ChiSurf and
is gated behind the demo-plugins switch like the rest of the games.

## What this is

A place to walk while a fit runs in the background — and the carrier for the
review-attachment phase. The progression state (XP, streaks, achievements)
already exists in the plugin's API but is deliberately **unused** by this
screen: wiring it to a walk would mean paying out for wandering. It attaches
to real review actions, not to movement.

The first draft of this window was an XP/streak form with a free-text path
field. It was replaced by the game because a form is not a game, and because
the no-text-entry rule exists exactly to prevent that sort of panel.

## Controls

- **Arrow keys / WASD** — walk.
- **Space / Return** — talk to an NPC, interact.
- **Escape** — release the keyboard back to the application.

The keyboard belongs to the game only while the canvas has focus; clicking
anywhere else in ChiSurf hands it straight back.

## The map

The overworld is a tile map built from the bundled art (`art/` in the plugin
directory; sources and licences are in `art/CREDITS.md`). NPCs, quests and the
beast behaviour live in the plugin's `api` modules, which carry their own
tests.

Press **Guide** for the walk-through.
