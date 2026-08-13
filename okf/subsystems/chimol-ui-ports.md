---
title: Porting a widget into chimol's chrome
status: in-progress
group: subsystems
updated: 2026-08-13
---

# Porting a widget into chimol's chrome

## Where to pick this up

**2026-08-13 — the code editor and the hex view landed, and the porting path
they exposed is now tooling.** What is open, in order:

1. **`.native` still exists in the chrome's Qt painter.** Nothing here made it
   worse, but the two new controls draw through `Painter`'s six operations
   only, which is the property the whole package rests on; re-run
   `test_engine_is_portable.py` before adding a third and treat a new Qt import
   at module scope as a blocker, not a note.
2. **The editors are not yet docks.** `cmd/inspect.py` opens them in their own
   top-level windows, deliberately (a dock has to be registered, persisted in
   the saved layout and given a View-menu entry, and none of that is what
   somebody typing `memory instances` is asking for). Promoting either to a
   dock costs nothing at the control level — it is the same object — but must
   go through `molview_main_window`'s dock list, which is the file most likely
   to be under concurrent edit.
3. **VRAM readback is untested against a real device.** `memory_probe`'s
   `GpuBufferSource` is covered by a fake queue. On a real `wgpu` device, a
   buffer created without `COPY_SRC` raises, and the *measurement* to take is
   how many of chimol's buffers actually carry it — if it is most of them, the
   fallback path is nearly dead code and the honest move is to say so in the
   picker rather than show a block of zeros.
4. **The scaffolder handles one shape of C++.** It reads Dear ImGui's house
   style (uppercase public methods, `IM_COL32` palettes, `static const char*
   const` word tables). It has not been run against anything outside that
   family, and the next port is where that either holds or does not.

## What this is

chimol's in-viewport chrome — `chimol/renderer/ui/` — is a **port**, not an
original toolkit. Sixteen control families came out of three MIT-licensed
sources by reading them and transcribing:

| family | source |
| --- | --- |
| `widgets`, `text`, `buttons`, `sliders`, `drag`, `inputs`, `color`, `combo`, `selection`, `menus`, `tabs`, `tables`, `dragdrop`, `layout` | Dear ImGui (`junk/imgui`) |
| `text_editor` | ImGuiColorTextEdit (`junk/ImGuiColorTextEdit`) |
| `memory_editor` | imgui_club's `imgui_memory_editor` (`junk/imgui_club`) |

Every one draws through `painter.Painter`'s six operations, holds its own
state, and takes as an **explicit argument** anything the chrome has no feed
for — hover, a clock, a click count. That is what lets the same object be drawn
by the GPU painter in the viewport, by `QtPainter` in a Qt form, and by the
browser build.

## The three pieces that make a port routine

Doing sixteen of these made the shape of the work obvious: about a third is
transcription of **data**, and it is the third where a mistake is silent — a
keyword dropped from a 200-word table colours one word wrong in one language
and fails nothing.

* **`renderer/ui/control.py`** — the contract as a class rather than as prose:
  remembered geometry, no-op `press`/`drag`/`release`/`key`/`scroll`, and
  `measure`. It is scaffolding for what comes next; the fourteen existing
  families are plain objects and are not being retrofitted.
* **`build_tools/dev_utils/port_imgui_widget.py`** — extracts the enums,
  palettes, option struct and keyword tables from the C++, emits the module
  skeleton with the four required docstring sections, writes the
  recording-painter test, registers the module in `CONTROL_MODULES`, and prints
  the public methods still to implement in source order. It deliberately does
  **not** translate statements: C++ machine-translated to Python runs and is
  wrong in a way that reads as intentional, which is worse than a stub.
* **`chisurf/plugins/chimol/test/recording_painter.py`** — one shared recording
  painter. Ten test modules had their own copy; identical copies are how the
  metrics quietly stop agreeing.

`renderer/ui/qt_host.py` is the fourth piece and the one that changes what a
port is *for*: any control becomes a `QWidget` without a second
implementation, because `chimol.host.keys` and `chimol.host.events` took Qt's
numeric values as the engine's own precisely so the translation would be free.

## The two new controls

### `text_editor` — a colourising, multi-cursor editor

A `Document` of `Line`s with four overlays, exactly the reference's layering:
`Colorizer` (per-character token), `Bracketeer` (pairs, coloured by nesting
level, unmatched in red), `Cursors` (main and current, VS Code semantics),
`Transactions` (undo with the caret state either side).

Three divergences from the reference, all deliberate:

* **A line is a string plus a colour `bytearray`, not a vector of glyph
  structs.** The literal port is one Python object per *character*.
* **Tokenizers are regular expressions, not re2c automata.** The reference
  generates scanners because a virtual call per character was too slow in C++;
  in Python a compiled pattern runs in C and a character loop does not.
* **`Color` is split.** `Token` carries only token roles; the chrome colours
  come from `style.py`, which already has a palette.

Not ported: word wrap, line folding, the minimap, autocomplete, LSP hover,
squiggles, line decorators, Annex-14 line breaking — all features of the
reference's *TypeSetter*, the layer that separates document position from
visual position. chimol draws one document row per screen row, so the port
keeps the single coordinate system and is a third of the size.

**One language is chimol's own.** `Language.chimol(commands)` is built from the
live command registry, so a command added to a `cmd` mixin colours as a keyword
without anybody editing a word list.

### `memory_editor` — a hex view over RAM and VRAM

The reference only ever addresses process memory. The addition here is a
`MemorySource` seam, so the same control draws a host array (sliced, free) or a
GPU buffer (**copied back** through the queue, which costs real time and
requires `COPY_SRC`). `renderer/memory_probe.py` enumerates them by walking the
live object graph rather than by keeping a registry of allocations — a registry
is only correct while every allocation site remembers it, and wrong silently
when one does not. Its report therefore says **"found"**, not "total".

## Where the ports surface

* **In the viewport** — as chrome controls, drawn by the GPU painter.
* **In a Qt form** — `code_editor` and `memory_editor` are AutoForm custom
  sections (`chisurf/gui/autoform/sections/`). `code_editor` is in the
  documentation generator's `CUSTOM_PARAM_KEYS` because it is something the
  user sets; `memory_editor` is not, because a hex dump is a view.
* **At the prompt** — `cmd/inspect.py` adds `memory` (report, list, hex dump,
  or a window) and `editor` (open a file, language from the extension).

## Rules a port must keep

1. **Read the source; do not infer.** Leave the `CHISURF-REVIEWED` /
   `-TAKEN` / `-SKIPPED` header in the checkout, header only — a `git diff`
   inside `junk/` must show insertions and zero deletions.
2. **Extract the data, do not type it.** The word tables in `text_editor.py`
   are generated, and a test re-extracts and compares them; that test is the
   only way anybody would find out they had drifted.
3. **Say what was skipped.** A reader must be able to tell "not ported" from
   "forgotten"; the module docstring's third heading is where that goes.
4. **Look at it.** A recording-painter test proves a control emitted the
   rectangles it meant to and nothing about whether the result is legible. Add
   a page to `test/widget_gallery.py` and read the PNG — the whitespace dots
   ported at the reference's own `(80, 80, 80)` were in the pixels and not on
   the screen, which only the image showed.
