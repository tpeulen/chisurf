---
type: Subsystem
title: Game engine (chigame)
description: The shared 2-D game engine on WebGPU — scene, orthographic camera, instanced sprite/SDF batcher, a nine-action abstract controller, synthesised audio, and the AssetPack seam that makes the whole look and soundtrack swappable.
resource: chisurf/gui/chigame/
tags: [gui, game, chigame, wgpu, wgsl, seam, audio, input]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

**Phase 1 in progress (2026-08-10).** The engine is being stood up alongside its
first consumer, the `pong` port. Read [PRD-91](../prds/prd-91.md) for what the
engine is ultimately for.

Next, in order:

1. **Finish the Phase-1 surface** — scene, camera, batcher, `InputMap`,
   `AssetPack`, audio, offscreen capture — and land `pong` on it.
2. **Four more ports, each forcing one capability**: breakout (sprite batching
   under load), tetris (tilemap grid + text), minesweeper (picking), number_quest
   (menu/UI). A port that needs something the engine lacks gets the engine
   extended — never a workaround inside the game. That rule is the whole point of
   porting them.
3. **Then the consumer that motivated it**: the top-down world of Lumis Quest.

# What it is

`chisurf.gui.chigame` is *the* 2-D game engine of the application, in the same
sense that [chiplot](chiplot.md) is the plotting API and
[chitable](gui-tables.md) is the table family. Games use it; they never touch
the graphics API directly.

It renders through **WebGPU** (`wgpu` + `rendercanvas`), embedded in an ordinary
Qt dock. WebGPU rather than OpenGL for the same reason the molecular viewer is
moving there ([chimol in the browser](../plugins/chimol-web.md)): macOS caps
OpenGL at 4.1 and deprecates it, and one shading language across desktop and
browser beats two.

# Why it is written rather than depended on

The obvious move was to depend on an existing wgpu render engine. It was cloned
to `junk/` and read instead. That engine is ~37,700 lines of Python and 33 WGSL
files spanning a full 3-D pipeline: materials, PBR, lights, shadows, bloom,
geometry primitives, animation, a text/glyph-atlas subsystem. A top-down 2-D game
needs a small fraction of it, and the fraction it needs is the *boilerplate* —
device and adapter setup, canvas context configuration, pipeline and bind-group
caching, the render-pass and present dance.

So the reference is mined for those patterns and the result is written in-tree.
What is taken and what is deliberately skipped is recorded in the checkout's own
headers (`CHISURF-REVIEWED` / `TAKEN` / `SKIPPED`) per the
[reference-checkout workflow](../workflows/reference-checkouts.md); this concept
is the durable record, because `junk/` is gitignored.

`wgpu` and `rendercanvas` **are** dependencies and are declared. They are the
graphics API and the platform surface plumbing — per-platform surface creation
(CAMetalLayer, X11/Wayland, Win32), the Qt event-loop marriage, and the offscreen
backend. That is platform quirk, not a page of code.

# The seams

Four, and they exist so that what a game says stays separate from how it looks,
sounds and is controlled.

## AssetPack — the look and the soundtrack are swappable

Games emit **semantic** draw calls and never name a texture, a colour or a shader:

    scene.draw("dye", "atto488", state="idle", at=(x, y))

An `AssetPack` resolves the semantic name to something drawable. The default
`ProceduralPack` renders signed-distance shapes in WGSL and ships with **no image
files at all** — creature colour is derived from a real emission maximum via
wavelength→sRGB, so the art is generated from data rather than drawn. An
`AtlasPack` backed by a sprite sheet can replace it later **without a line of game
code changing**.

A pack declares its tiles, palette, sprite mappings, shaders **and music** in one
manifest. Music lives in the pack deliberately: swapping the pack swaps the
soundtrack with the art, because a look and its score are one artistic decision.

## InputMap — nine actions, no text

The engine exposes an abstract controller: four directions, Confirm, Cancel, Menu,
and two shoulders. Games bind to *actions*, never to keys or buttons.

This is a design constraint, not a convenience. Everything built on chigame must
be playable on a gamepad, which means **no heavy text entry anywhere** — free-text
input has to become selection, and selection produces structured data. Keyboard
bindings ship first; a pad backend slots in behind the same seam without touching
a game. Nothing gamepad-capable is currently installed (this Qt5 build has no
`QtGamepad`, and Qt6 removed the module), so that choice stays open.

Because actions are abstract, input is trivially scriptable — a headless test
drives a game by pushing actions, with no synthetic key events.

## Audio — synthesised, context-switched

No audio binaries either. The pattern already existed in the tree, duplicated
three times: the arcade games each synthesise WAV programmatically (`math`,
`struct`, `wave`) and play through `QSoundEffect`. Those consolidate here into a
small chiptune sequencer — waveform generators plus ADSR envelopes, a track as
JSON note data, synthesised once at load.

Music is **context-driven**: `audio.set_context("overworld" | "town" | "battle" |
"underworld" | "victory")` crossfades. Games set a context; they do not manage
playback.

## Offscreen capture — headless is a first-class path

`rendercanvas.offscreen` renders real pixels with no window server, which is what
makes the project's rule that a GUI is never implemented blind
([testing workflow](../workflows/testing.md)) achievable for a game.

**Known divergence**: under `QT_QPA_PLATFORM=offscreen` a `QRenderWidget` yields a
bitmap context rather than a surface context. A headless screenshot therefore
proves the *scene*, not the swapchain or presentation.

# Traps

- **`rendercanvas.qt` raises on import** unless a Qt binding is imported first.
  `import PyQt5.QtWidgets` (or `qtpy`) must precede it. The error reads like a
  missing dependency and is not one.
- **Qt binding order matters**, so the engine's own import must establish it
  rather than leaving each game to remember.
- A `QRenderWidget` is a real `QWidget` (verified: it subclasses `QWidget` under
  PyQt5 and returns a wgpu context), so it docks, themes and grabs like any other
  widget — but it owns its own draw scheduling, and mixing Qt painting into it is
  not supported.

# Consumers

- The five arcade games in `chisurf/plugins/misc/games/` — being ported off
  `QPainter`, each one chosen to force a different engine capability.
- **Lumis Quest** ([PRD-91](../prds/prd-91.md)) — the top-down JRPG the engine
  exists for.
- Candidate, not committed: the molecular viewer's WebGPU work
  ([chimol in the browser](../plugins/chimol-web.md)) shares this stack, and the
  reason to put chigame in `chisurf/gui/` rather than inside a plugin is so the
  tree does not grow two independent WebGPU layers.
