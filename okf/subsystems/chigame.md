---
type: Subsystem
title: Game engine (chigame)
description: The shared 2-D game engine on WebGPU — scene, orthographic camera, instanced sprite/SDF batcher, a nine-action abstract controller, synthesised audio, and the AssetPack seam that makes the whole look and soundtrack swappable.
resource: chisurf/gui/chigame/
tags: [gui, game, chigame, wgpu, wgsl, seam, audio, input]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

**The real "tiles are shit" cause: the importer transposed Godot's atlas
coords (2026-08-15, commit 2d6d8d9a4).** The layer-order fix above was real
but only half the story. `import_ninja_map` decoded `atlas_y = int2 >> 16`
and `atlas_x = int3 & 0xFFFF` — swapped: Godot's `tile_map.cpp` packs the
triplet as int2 = `source | atlas_x<<16`, int3 = `atlas_y | alternative<<16`.
Every tile therefore drew from the wrong sheet cell (roofs where grass
belongs, a sand wash where the village is), and 111 cells whose transposed
coords fell outside defined atlas cells were silently dropped ("dead-cell
census": 111 under the swap, 0 under the correct decode — the census is the
cheap first probe for any future importer doubt). With the fix the render is
**99.3% byte-exact against the author's own art** (remaining 0.7% is the
HUD). Two traps made the earlier verification bless this wrong render, and
both live in any future per-pixel verifier: (a) walking the ground truth in
*draw* order re-derives the renderer's mistake — walk source-data layers
topmost-first; (b) sample pixel **centers** (`(px + 0.5 - W/2)/scale`), not
corners — the GPU samples centers, and corner sampling alone moved agreement
from 88.8% to 99.3%. Also ported with it: the teleporter's real arrival
semantics (`character.gd`: land at `target + (player − source) +
target.direction*25` — the port had used the *source's* direction, mirroring
her 25 px to the wrong side). Still not ported: wall-layer y-sort with
actors, below.

**Tile stacking fixed by the reference's own z-indices (2026-08-15).** The
`67ab53442` "layer order" fix was inverted: it read "Godot layer 0 is the
front" correctly but then *built* the TileMaps in ascending index order, which
paints the ground sheet **last** — every roof, tree and bush in the village
ended up buried under plain sand (the user saw "tile broken": uniform bands
where structures belong). The authority is the reference's base map scene
`system/map/map.tscn`, which pins the stacking explicitly: `layer_3 "Floor"`
at `z_index -2`, `layer_2 "FloorDetail"` at `-1`, layers 0/1 (`"Wall"`) on
top, y-sorted. `ninja_adventure/game.py` now builds the layers in descending
index order — ground painted first, canopy over it — verified per-pixel
against the converted map (the ground-truth walk must take layers *topmost
first*, i.e. reversed draw order; walking it in draw order just re-derives
the renderer's own mistake). Still not ported: the reference y-sorts the wall
layers *with the actors* (`y_sort_origin -5`), so a player behind a house
should be occluded by its front wall; chigame draws all tiles under actors.

**The reference game itself is playable now (2026-08-14, T-20260814-05).**
`chisurf/plugins/misc/games/ninja_adventure/` runs the author's own village
map: ``build_tools/dev_utils.import_ninja_map`` converts the Godot scene to
shipped JSON (tile triplets decoded, dead atlas cells dropped, collision
polygons → solids, Curve2D points → patrol waypoints), and the game plays it
on the ported systems — the authored spawn, the pig-follows-samurai-follows-
you chains, the patrol with its waits, 48 destroyables, the paired
teleporter, weather areas. Hostile samurai (the checkout ships no enemy
scene) sense, chase and swing on the author's enemy team. The port forced two
engine fixes now pinned in `test/gui/test_chigame_port.py`:
`GameHost.bind_pack()` (a pack swapped on `scene.pack` alone left the batch
sampling the old texture — every sprite flat white) and `Weapon` anchoring
its damage area in `update()` (an undrawn enemy weapon struck from a stale
origin) with a recharge so polled swings cannot machine-gun. pygame is **not**
an option for the engine (user rule); the pyzelda-rpg checkout is annotated
read-and-skipped.

**The NinjaAdventure port landed (2026-08-14, ticket T-20260814-05).** The
engine now has the reference game's systems, not just its renderer:

- `atlas.py` + `assets/pixel/` + `pack.py` — one RGBA texture atlas built at
  load from the vendored CC0 pack (credited in `assets/pixel/CREDITS.md`),
  sliced into named sub-frames; `SheetPack` resolves the AssetPack vocabulary
  to atlas frames and falls through to the procedural look for names it does
  not carry. `GameHost` binds a pack's atlas automatically.
- `actors.py` — the character stack: accel/decel bodies with axis-separated
  collision, the 4-direction x 7-row sheet animation (walk rows 0-3, attack 4,
  airborne 5, downed 6, six cells a second), `Health`/`Team`/`Damage`,
  `Weapon` swings with a hit-once `strike()`, `Destroyable` crates with
  knockback and burst. All tested in `test/gui/test_chigame_port.py`.
- `behavior.py` — follow-with-comfort-band, waypoint patrol with wait modes,
  radius sensing, wander.
- `tilemap.py` — numpy tile grid to one bulk instance array per frame, with
  solid lookup.
- `camera.py` — `RoomCamera`: the view locks to a 320x176 room grid and glides
  between rooms (0.8 s sine), snapping on teleport. Room *centres* sit at
  multiples of the room size — a room whose centre lands between cells
  rounds the wrong way under banker's rounding, so compose maps onto cell
  centres (see `test/gui/renders/chigame_port_demo.py`).
- `fx.py` — screen-fade `Transition` and `Weather` (rain/snow/leaves/clouds/
  fog), with a `particles()` accessor for games that draw weather through
  their own sprite names rather than the pack vocabulary.

The demo render (`test/gui/renders/chigame_port_demo.py`) composes one room
through every system and is the fastest way to see the port working.

**Lumis Quest's cast is the pack art now.** `gui/sheetart.py` answers the
game's sprite names (`iris_down_1`, `warden_0`, `hearts_a_4`) with sheet
frames inside the game's own atlas pipeline (`pixelart.build_atlas(resolver=...)`),
so tints, mirrors and footprints are untouched and the whole overworld test
surface holds. This reverses the 2026-08-14 morning handover in PRD-91
("iris should be no ninja") — the evening direction was "use all from ninja
game"; see the PRD for the record.

Next, in order:

1. **Commit the overworld half.** The re-skin edits in `overworld.py`,
   `pixelart.py` and `test/capture.py` are interleaved in the working tree
   with a peer agent's uncommitted rename work (constants `_IRIS_*` →
   `_PLAYER_*`, `game.iris` → `game.player_pos`) and cannot be committed
   separately; they land as one commit once the peer's work lands. The tree
   state is green (444 games+engine tests).
2. **A gamepad backend** behind the existing `InputMap`. Nothing is installed
   (this Qt5 build has no `QtGamepad`; Qt6 removed it), and every game is already
   written against the abstract actions, so this is additive.
3. **A second `AssetPack`** — now half-answered: `SheetPack` and
   `ProceduralPack` coexist behind one vocabulary; the remaining proof is a
   third look, not a second.
4. **Buildings from the village sheet.** Lumis Quest's houses come from a
   different CC0 pack (`gui/art/bigart.png`); composing them from the same
   ninja village sheet as the tiles would unify the look.

**What the five ports actually taught**, since that was their purpose:

- Every one of them needed *layout* room the first draft did not give it. Text
  clipped at a view edge three separate times (breakout's lives, tetris' help
  lines, number_quest's status line), and minesweeper sized its camera from the
  board's **height** alone, which fits the square Beginner preset and cuts the
  30-column Expert one straight off the sides. A view has to be sized from the
  widest thing in it, not the tallest.
- Local multiplayer needed a second controller, not more actions
  (`GameHost.add_player`).
- A gamepad has no key auto-repeat, so any game with a held direction has to
  implement repeat itself. Three of the five do.
- Nothing needed a mouse. Minesweeper was expected to force pointer picking and
  instead showed that a **cursor which is game state** is both exact by
  construction and trivially scriptable — there are no synthetic pointer events
  anywhere in the tests.

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
files at all**. An `AtlasPack` backed by a sprite sheet can replace it later
**without a line of game code changing**.

### The art direction is a rule, not a mood

The default pack is an **optical bench in a darkened room**, not an arcade
cabinet. One rule generates the whole look:

> Structure is desaturated graphite, steel and chrome. **Every saturated colour
> in the game is a wavelength**, produced by `wavelength_to_srgb` rather than
> picked. Anything that glows is emitting; anything grey is hardware.

That is worth more than a style guide, because it makes the picture *mean*
something. A brick wall becomes an emission spectrum. A ball becomes a photon
whose colour records the last band it interacted with. Two paddles become a
donor and an acceptor, and the ball changing colour as it crosses the field is
the transfer, not a flourish.

It also removes arbitrary decisions. `spectral_band(fraction)` gives a series of
distinct colours from the spectrum, and `photon_energy_rank(nm)` ranks them by
`1/λ` — so when a game needs a difficulty ordering, "bluer" and "harder"
coincide as a *consequence* instead of two unrelated facts a player must
memorise. Note the ranking is deliberately non-linear: the midpoint wavelength
of the visible range sits at energy rank 0.37, not 0.5.

The vocabulary a game draws with is therefore optical — `photon`, `band`,
`optic`, `detector`, `mount` — rather than `sprite` or `brick`.

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
small sequencer — a track is JSON note data, synthesised once at load.

Music is **context-driven**: `audio.set_context("overworld" | "town" | "battle" |
"underworld" | "victory")`. Games set a context; they do not manage playback.
A game whose context is a **property** rather than a class attribute changes
what is playing as the player moves, which is what the five contexts are for —
`OverworldGame.music_context` returns town inside the walls, battle in a fight
and underworld in the dark manifold.

**Two things make the difference between a sequencer and music**, and both were
missing until 2026-08-11:

* **Band-limited oscillators.** A square or saw built from a sign flip has
  energy far above Nyquist; at the old 22.05 kHz that folded straight back down
  as a metallic buzz no amount of composing could fix. Waveforms are now
  additive — a bounded harmonic series, cut off below Nyquist — at 44.1 kHz,
  with a vibrato option, an optional detuned second oscillator, an ADSR with a
  real decay, a gentle lowpass over the mix (`tone`), and `tanh` soft clipping.
  A drum voice (kick/snare/hat as a pattern string) sits under the tracks that
  want one. Synthesis is numpy, so a whole soundtrack builds in ~0.4 s.
* **Pieces, not patterns.** A note may be `[semitone, eighths]` or `null` for a
  rest, so a line can hold and breathe. The shipped tracks were sixteen
  unbroken eighth notes — a four-second loop with no rest, no held note, no
  harmony and no cadence, which is unlistenable inside a minute however
  pleasant the intervals. They are now eight bars with phrase structure and a
  bass line following a chord progression: twelve to twenty seconds a loop.

**The soundtrack is real recorded audio, and it fits in the repository.** Five
seamlessly looping tracks and 512 sound effects by **Juhani Junkala**
(SubspaceAudio), both **CC0**, live in `audio_assets/` as two zips of IMA ADPCM
clips -- mono, 22.05 kHz, four bits a sample. That is **6.7 MB** against 27 MB
for the source WAVs, which is the difference between a soundtrack that is
committed and one that is a download step. `adpcm.py` is the codec: IMA is
sequential by nature, so the stream is cut into independent blocks each
carrying its own starting predictor, and every block is then decoded *in
parallel* with numpy -- a minute of audio in milliseconds rather than a Python
loop over millions of samples. `build_tools/dev_utils/pack_game_audio.py` is
the one-off developer tool that produced them; nothing at runtime imports it.

Two seams keep this swappable and optional. A track names a recording with
`"clip"` **and keeps its note data**, so a stripped install degrades to the
synthesiser rather than to silence. And a game asks for an *event*
(`"paddle"`, `"unbind"`), which `AssetPack.sound_clip` maps onto a particular
recording -- so a game's vocabulary never has to know what is installed, and a
name with no entry still falls through to a synthesised blip, which is why
every call site still passes a frequency. `audio_assets/CREDITS.md` carries the
author's own licence statement verbatim: CC0 asks for nothing, but a package
that redistributes somebody's work should say whose it is, in their words.

**The decoder has a GPU route** (`wgsl/adpcm.wgsl`), one invocation per block,
and it is the default wherever an adapter exists. Both routes are kept and are
asserted **bit-identical** -- the codec is lossy, so a route that decoded
differently would change the audio behind the caller's back, which is worse
than being slow. The host lends the renderer's device rather than asking the
driver for a second one to decompress audio.

`MIN_BLOCKS_FOR_GPU` is **zero**, and that inversion is worth reading before
changing it: the guess was 600, on the reasoning that a ~1.7 ms dispatch cannot
be worth it for a 50 ms sound effect. The measurement disagreed, because the
numpy route has the *larger* floor -- it runs `BLOCK` vectorised steps whatever
the clip's length, so a three-block clip still costs ~10 ms of numpy call
overhead. See [benchmarks](../../docs/development/benchmarks.md).

**A track may be a tracker module** (`{"module": "song.mod"}`), rendered by
`tracker.py` -- an in-tree ProTracker player, no dependency. This is the only
audio format small enough to live in a source tree: a module stores a handful
of short instrument samples plus a grid of which note plays on which channel on
which row, so a four-minute song is 50--300 kB against tens of megabytes as
OGG -- the same order as the PNGs already committed. `libopenmpt` is the usual
answer and is **not on conda-forge at all**, so using it would mean vendoring a
C library into a scientific package to play a tune; the format is old, small
and fully documented, and the player is a page of parsing and a page of mixing.
It renders to exactly the PCM the synthesiser produces, so a module drops into
the existing `QSoundEffect` path with nothing else to change, and a missing or
unreadable module falls back to the track's note data rather than to silence.

Supported: 31-instrument MOD (`M.K.`/`M!K!`/`4CHN`/`6CHN`/`8CHN`), Amiga periods
against the PAL clock, linear interpolation, and the effects that change what
you hear -- portamento, tone portamento, vibrato, sample offset, volume slide,
position jump, set volume, pattern break, speed/tempo. Anything else is parsed
and ignored, which is deliberate: an unknown effect must not silence a channel
or desynchronise the song. `Module.credits` exposes the title and sample names,
because a tracker author's attribution lives in the sample names and a CC-BY
module needs that text to reach a credits screen rather than being discarded.

**A game in a window nobody is looking at is silent.** `Audio.suspend()` /
`resume()` hold playback and remember the context, and `GameHost.sync_audio()`
drives them from `GameHost.attend()` — visible, and in the active window. It is
called both per frame *and* from a Qt event filter installed by `create_widget`,
because a hidden widget may stop being asked to draw at all, and a game whose
frames have stopped with its music still playing is the worst version of this
bug.

## pixelfont — the typeface is string art, not a font file

`pixelfont.py` holds all 95 printable ASCII glyphs as eleven rows of seven
`#`/`.` characters, and `text.py` uploads them as one coverage atlas. There is
no font file, no font parser, and no Qt in the text path at all, so a headless
render and a windowed one draw identical glyphs.

**Why 7x11 and not 5x7.** A 5x7 body is a Game Boy face — one stroke per
feature and no room for a curve to be a curve. The taller box gives capitals
eight rows, lower case a real x-height, and `g j p q y` somewhere to descend to.

**Two things matter as much as the resolution**, and both are what separate a
console face from a terminal one:

- **Proportional widths.** Glyphs are authored in a 7-wide box and *trimmed to
  their ink*, so `i` takes one column and `m` seven. The advance is measured
  from the art, never declared beside it — a hand-kept width table goes wrong
  silently the first time a stem moves.
- **A drop shadow.** Every string is drawn twice, one font pixel down and
  right, in a dark tone. It is why console text stays readable over any
  background. Tests that count text lines must filter the shadow pass out.

It replaced Qt rasterisation, which carried a real bug:
`QFontDatabase.systemFont(FixedFont)` resolves to `.AppleSystemUIFont` on
macOS — a *proportional* face — and `setFixedPitch(True)` afterwards does not
change what was already resolved, so narrow letters floated in cells the width
of an `M`. The glyph atlas is also sampled **nearest** now; a pixel font
through a linear filter is a blurred pixel font.

Licensing, since this replaced a proposal to ship a real one: `joystix.ttf` was
refused after reading its `name` table — `© Typodermic Fonts Inc`, trademarked,
no licence grant, whatever the surrounding repository's MIT file says. (The
*graphics* of that same reference are genuinely CC0 — the Ninja Adventure pack
by Pixel-boy and AAA.)

## Where the art comes from — and the one rule about it

chigame ships **no image files**: the procedural pack renders signed-distance
shapes, and `pixelfont` is string art. Lumis Quest is the one exception, and it
is a deliberate one: its **ground tiles** are cut from the **Ninja Adventure**
pack by Pixel-boy and AAA, which is **CC0** — a public-domain dedication, so
nothing propagates into ChiSurf's GPL and no attribution is owed (it is given
anyway, in `gui/art/CREDITS.md`).

Only the ground. Every building, character and creature stays string art,
because the bestiary's whole premise is that one hare drawing is a Verdant Hare
and a Garnet Hare depending on the dye somebody fixed into it, and no generic
pack supplies that.

**The rule, learned the expensive way**: a shipped art pack is cut by a script
from a `junk/` checkout and committed, never read from `junk/` at run time —
that directory is gitignored, so anything reading from it works on one machine
and nowhere else. `build_tools/dev_utils/import_tileart.py` records the source
cell of every tile and can re-cut them, so the provenance of each shipped pixel
is a command rather than a claim.

Three things only the rendered world showed:

- The palest tile in a *natural*-ground sheet is snow, so a town square got
  paved in snow. Made ground comes from the interior sheet.
- A tile block's plain fill is a **flat colour**, which trips the project's own
  "terrain is dithered rather than flat" guard — and pairing it with a rippled
  tile makes the whole sea blink instead of move.
- Every authored prop had the old grass painted in behind it. That was
  invisible while the ground was the same string art, and became a hard square
  under every tree the moment it was not. Props are **composited over the
  shipped ground at atlas-build time**, because a tree is a *cell of the grid*
  rather than a sprite over a grass cell: clearing its backdrop leaves a hole,
  since there is nothing beneath it.

Loading degrades to the string art if the pack is missing, which is right at
run time and wrong to discover in a release — so a guardrail test asserts the
art is present and is what `sprite_image` returns.

## Scene.window — the console dialogue box

Three flat bands, outside in: a near-black outer edge, a bright rule one pixel
inside it, then a saturated fill. The **rule** is the whole effect — it is what
makes a box sit *on* the picture rather than float over it, and it is what a
single translucent rounded rectangle can never give you however carefully it is
tinted. Two extra quads.

## ParticleField — the layer that says something happened

`particles.py` is a `Field` of `Particle`s, each of which is one of three
things depending on which fields are set: a **number that rises and fades**, an
**orb that flies to a target**, or a **one-shot burst**. Ported from a small
MIT-licensed pygame RPG (`junk/pyzelda-rpg`, headers on the files read), which
had all three and is the reason they exist here at all — a game without them
makes the player read a bar to find out whether anything happened.

The look stays semantic: a particle names a `kind` and a `name` and the
`AssetPack` decides, exactly as `Scene.draw` does. `alpha` is now a
**Scene-level hint** rather than a pack concern — it scales whatever opacity
the pack chose, so anything can fade without teaching every branch of every
pack about transparency.

Three things are deliberately not the way the reference had them, each because
the reference's version has a failure mode that does not show up on the machine
it was written on:

- **Motion is integrated against `dt`**, not counted in frames. Frame-locked
  particles live proportionally longer on a slow machine.
- **The field has a cap.** An emitter inside a loop is the standard way a
  particle system becomes a frame budget.
- **`burst(radius=...)` can spawn a ring.** A spark thrown from the middle of
  something that is already glowing spends its whole life inside that glow. No
  assertion says so; a screenshot does, and did.

## Offscreen capture — headless is a first-class path

`rendercanvas.offscreen` renders real pixels with no window server, which is what
makes the project's rule that a GUI is never implemented blind
([testing workflow](../workflows/testing.md)) achievable for a game.

**Known divergence**: under `QT_QPA_PLATFORM=offscreen` a `QRenderWidget` yields a
bitmap context rather than a surface context. A headless screenshot therefore
proves the *scene*, not the swapchain or presentation.

# Traps

- **A failing `draw` used to vanish.** The canvas catches whatever its draw
  callback raises, logs it, and hands back an empty frame — so a plain
  `NameError` in a game surfaced much later as an `IndexError` on a
  0-dimensional array, somewhere unrelated. `capture` now captures the
  exception and re-raises it, and refuses a frame that is not an image.
- **Colour above ~645 nm stops changing.** The hue is already pure red, so
  without a brightness gradient every wavelength from there to 780 renders
  *identically* — two spectral bands 40 nm apart looked the same. The rolloff
  therefore starts at 620, which is both the fix and closer to real luminous
  efficiency.
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
