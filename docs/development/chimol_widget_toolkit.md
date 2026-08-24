---
type: Development Note
title: cmtk — the in-viewport toolkit
description: How to write a panel or add a control with cmtk, the canvas toolkit ChiMOL draws inside the 3-D viewport.
tags: [development, chimol, cmtk, gui]
audience: developer
---

# cmtk — the in-viewport toolkit

ChiMOL draws its own interface inside the 3-D viewport rather than around it,
so the same code serves the desktop Qt build and the browser build. This page
is for someone writing a panel with that toolkit, or adding a control to it.

The controls live in `modules/chimol/chimol/cmtk/` — **cmtk**, the
**Canvas Model Toolkit**, chimol's in-viewport widget/plot namespace. ChiSurf
reaches cmtk **via chimol**, and chimol independence
([`okf/plugins/chimol-relocation.md`](../../okf/plugins/chimol-relocation.md))
comes first — the ChiSurf↔cmtk interface is still floating. Until 2026-08-13 the
widgets lived in a sibling package called `renderer/ui/`; that package was
merged into `cmtk/` so chimol has one widget namespace, alongside the plotting
port `cmtk` also carries — see `okf/plugins/chimol-cmtk.md`; a
view-orientation gizmo was tried and removed the same day, also recorded
there. The widgets
are a port of [Dear ImGui](https://github.com/ocornut/imgui)'s widget stack —
its look and its arithmetic, in plain Python, drawn through ChiMOL's own
painter. It is not a binding: no imgui code runs, and nothing links against
it.

## The painter is six operations, plus one for what a rectangle cannot draw

Every control draws through `cmtk/painter.py`, which offers
`fill_rect`, `stroke_rect`, `gradient_rect`, `text`, `push_clip`/`pop_clip`,
and two measurements, `text_width` and `line_height`. There is no circle, no
image, and no rotation.

That is a deliberate floor, not an oversight: it is the largest set a triangle
rasteriser serves directly, so the same control paints as GPU quads, through
`QPainter`, and in a browser canvas without a second implementation. Anything
round is scan-converted from rectangles — `style.disc` is the shared helper —
and anything the floor genuinely cannot express was left unported rather than
faked (see *What is not here*).

The floor grew one operation, `fill_triangle` — three independent corners,
flat-shaded, no outline — when chimol's in-viewport toolkit gained a plotting
library (`okf/plugins/chimol-cmtk.md`), which needed what a rectangle cannot
express: a diagonal line, a scatter marker. It is additive to this floor,
not a reversal of it — every control in
this document still draws with the original six, and `line()` (a thin quad,
two `fill_triangle` calls) is a free function, not a `Painter` method, so a
new backend still implements exactly seven methods.

## A control is a retained object

The reference is immediate-mode: you call `ImGui::Button("Apply")` every frame
and a global context remembers what happened. ChiMOL is immediate-mode *in
style* and retained *in implementation*. A control is an object that keeps its
state, its hit test and its drawing in one place:

```python
from chimol.cmtk import SliderFloat

gain = SliderFloat("gain", 0.0, 1.0, 0.35)      # construct once, keep it

gain.draw(painter, x, y, w, h)                   # paint into a box
gain.press(px, py, x, y, w, h)                   # a press that landed in it
gain.drag(px, py, x, y, w, h)                    # -> True if the value moved
gain.release()
```

`press` returns something you can act on rather than a bare bool wherever there
is something better to return: the new value for a value control, an index or
`None` for a picker, a small record for a menu.

**There is one paradigm.** Do not add an immediate-mode context beside this
one. Where the reference reads its per-frame global for something ChiMOL has no
feed for — hover, a clock, a modifier key, a click count — the port takes it as
an explicit argument instead:

```python
row.press(px, py, *box, ctrl=True, shift=False)   # modifiers are arguments
tip.hover(px, py, now=time.monotonic())           # so is the clock
```

## Laying a panel out

`layout.Layout` is the reference's cursor, as an object you thread through
rather than a global. It removes the `y += row_h` bookkeeping every panel used
to repeat:

```python
from chimol.cmtk import Layout, Checkbox, Button

cursor = Layout(painter, x, y, w, h)
Checkbox("cull", True).draw(painter, *cursor.row(width=90.0))
cursor.same_line()
Checkbox("fog", False).draw(painter, *cursor.row(width=90.0))
cursor.indent()
gain.draw(painter, *cursor.row())
cursor.unindent()
Button("Apply").draw(painter, *cursor.row(width=80.0))
```

`same_line()` and `same_line(offset)` follow different rules — the reference's,
not one generalised rule — so an explicit offset is measured from the box and
adds no default gap. `begin_group()`/`end_group()` measure a run of items as
one, and `content_height()` is what tells you whether you need a scrollbar.

## What is where

| Module | Controls |
|---|---|
| `widgets` | the original nineteen: `SliderFloat`, `Checkbox`, `Combo`, `Button`, `ProgressBar`, `TreeNode`, `Separator`, `Toggle`, `RadioGroup`, `InputInt`, `ListBox`, `Tabs`, `PlotLines`, `Histogram`, `Tooltip`, `TextInput`, `Table`, `ColorEdit4`, `ScrollBar` |
| `text` | `Text`, `TextColored`, `TextDisabled`, `TextWrapped`, `LabelText`, `Bullet`, `BulletText`, `SeparatorText`, `TextLink`, `Value` |
| `buttons` | `SmallButton`, `InvisibleButton`, `ArrowButton`, `CheckboxFlags`, `RadioButton` |
| `sliders` | `SliderInt`, `VSliderFloat`, `VSliderInt`, `SliderAngle`, `SliderFloatN`, `SliderIntN` — linear or logarithmic |
| `drag` | `DragFloat`, `DragInt`, `DragFloatN`, `DragIntN`, `DragFloatRange2`, `DragIntRange2` |
| `inputs` | `InputFloat`, `InputDouble`, `InputScalarN`, `InputTextWithHint`, `InputTextMultiline` |
| `color` | `ColorButton`, `ColorEditRGB`, `ColorEditRGBA`, `ColorPicker3`, `ColorPicker4`, `rgb_to_hsv`/`hsv_to_rgb` |
| `combo` | `ComboBox` — the drop-down list |
| `selection` | `Selectable`, `CollapsingHeader`, `SelectableList`, `MultiSelectState`, `TypingSelect` |
| `menus` | `MenuItem`, `Menu`, `MenuBar`, `Popup`, `PopupModal` |
| `tabs` | `TabBar`, `TabItem`, `TabItemButton` |
| `tables` | `Column`, `DataTable` — sizing policies, resize, reorder, multi-sort, hiding, frozen panes |
| `dragdrop` | `DragDropSource`, `DragDropTarget`, `DragDropContext`, `Payload`, `DelayedTooltip` |
| `layout` | `Layout`, `LayoutStyle` |
| `style` | the palette, `hit`, `clamp`, `lerp_colour`, `disc`, `fit_text`, `format_value` |

Every name is importable from the package directly — `from ...cmtk
import DragFloat` — which resolves it lazily from whichever module owns it, so
putting one slider on screen does not import the whole toolkit.

### `Combo` cycles, `ComboBox` opens

Two controls, deliberately both kept. `widgets.Combo` is one row that steps to
the next option when clicked — no popup, no viewport needed — which is what a
dense settings panel wants for a four-option enum. `combo.ComboBox` is the
reference's real combo: it opens a scrolling list, caps its height in *items*
(the default is 8, not "all of them"), and flips above the frame when there is
no room below. Reach for `ComboBox` when the options need reading before
choosing, and for `Combo` when they do not.

### A drag is not a slider

The distinction is worth stating because the two look alike and behave nothing
alike. A **slider** maps an absolute position in its box to a value. A **drag**
has no track: the value changes by the pointer's *delta* since the last event,
scaled by `v_speed`, and the box is only where the gesture starts. `drag.py`
ports the reference's accumulator along with it, which is what makes a slow
sub-pixel drag of an integer eventually move by one instead of rounding to zero
forever.

## Two colour rules

**Name a colour, never write one.** `style.py` holds the palette; a module that
keeps its own `(66, 150, 250, 240)` drifts from the rest one tweak at a time and
nothing fails when it does. `style` also records which of ChiMOL's colours
differ from the reference's and why — its checkmark is green rather than the
accent blue, for instance, so "this is on" and "this is selected" do not share
a colour.

**Only draw glyphs the atlas has baked.** The Qt painter draws with a font, the
GPU painter draws from `cmtk/atlas/`. A character the atlas lacks
therefore looks perfect in every screenshot and paints as **nothing** in the
app — no exception, no warning. The baked non-ASCII set is:

```
… ─ ■ ▴ ▶ ▸ ▼ ▾ ◀
```

Spell a symbol with one of those or with ASCII. Widening the atlas costs
texture area the chrome re-uploads on every repaint, so it is the last resort,
not the first. `test/test_chrome_atlas.py` fails the build on any module in
`cmtk/` that draws an unbaked character.

## Looking at what you built

Assertions cannot see a clipped label, a caption drawn over its neighbour, or a
grab that covers the text underneath it. Render the sheet and read it:

```bash
QT_QPA_PLATFORM=offscreen \
    python -m chisurf.plugins.chimol.test.widget_gallery
```

One PNG per family lands in `chisurf/plugins/chimol/test/renders/widget_gallery/`.
There is no golden image to diff — the point is that a person looks. Adding a
control means adding a row to `_BUILDERS` in that module.

## Testing a control

Controls are tested against a **recording painter** that stores the six
operations instead of performing them, so the suite needs no GUI toolkit at
all; a control that quietly grows a Qt dependency fails there first. Copy
`RecordingPainter` from `test/test_ui_widgets.py`.

Assert behaviour, not the absence of a crash. "It painted something" is worth
very little; "a drag of the same distance from two different starting points
produces the same change" is what proves a drag is not a slider.

## What is not here, and why

Four things in the reference were deliberately not ported. Each is recorded in
the `CHISURF-SKIPPED` headers on the reference checkout so the reasoning is not
re-derived:

- **`Image` and `ImageButton`** — the painter has no image operation. A
  coloured rectangle standing in for a texture is a control that silently draws
  the wrong thing.
- **The colour wheel** — an annulus of shaded arcs plus a rotating barycentric
  triangle, from axis-aligned rectangles only. The reference's own default, the
  saturation/value square with a hue bar, *is* expressible and is what shipped.
- **Box-Select** — its update is a per-frame difference against the previous
  frame's rubber band. A retained model has no previous frame to difference
  against; a snapshot-at-drag-start equivalent is a different algorithm and was
  not added under the same name.
- **Keyboard navigation, docking, and `.ini` persistence** — all of these are
  the per-frame global context, which is the thing this design does without.

Rounded corners are absent throughout for the same reason as the rest: the
painter draws rectangles.
