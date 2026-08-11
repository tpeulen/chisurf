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

**Phases 1 and 2 are done: all five arcade games are on the engine**, off
`QPainter`, each verified against a before/after screenshot pair in
`chisurf/plugins/misc/games/test/renders/`.

Next, in order:

1. **The consumer that motivated the engine**: the top-down world of Lumis Quest
   ([PRD-91](../prds/prd-91.md)) — toctree → regions → villages → rooms, then
   combat, then the AI layer.
2. **A gamepad backend** behind the existing `InputMap`. Nothing is installed
   (this Qt5 build has no `QtGamepad`; Qt6 removed it), and every game is already
   written against the abstract actions, so this is additive.
3. **A second `AssetPack`** would be the real proof that the seam holds. The
   procedural pack is the only implementation today, so "swappable" is so far an
   argument rather than a demonstration.

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
