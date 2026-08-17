---
title: cmtk — Canvas Model Toolkit
status: in-progress
group: plugins
updated: 2026-08-14
---

# cmtk — Canvas Model Toolkit

**Name (2026-08-14): `cmtk` = Canvas Model Toolkit.** Earlier spellings —
"Canvas & Model Toolkit", "Component / Canvas Molecular Toolkit", "chimol
toolkit" — were approximations; the maintainer's plain statement wins:
**canvas model toolkit.**

**Order of operations (2026-08-14): chimol independence comes first.**
ChiSurf reaches cmtk **via chimol** — the interface between ChiSurf and cmtk
is still floating, and making chimol independent
([chimol-relocation.md](chimol-relocation.md)) must happen first anyway. The
dependency direction is: ChiSurf imports chimol; chimol may not import
ChiSurf; cmtk lives inside chimol and ChiSurf consumes it through chimol.

Tracked by [PRD-104](../prds/prd-104.md); read that first for the phased scope
and the one architecture decision (an arbitrary filled triangle added to
`Painter`). This concept carries the working state and resume point as each
phase lands.

**Naming, corrected (2026-08-13 + 2026-08-14): `cmtk` is the one name.**
Canonical expansion: **Canvas Model Toolkit** (2026-08-14). Not a "tk"
package with a "cmtk" alias. It runs on the **existing** GL/GPU toolkit — the
`Painter`/`QtPainter`/`QuadPainter` seam, unchanged in its own identity —
cmtk just adds widgets to it.

**First external consumer (2026-08-14): chiplot.** The maintainer directed
that chiplot's native backend **MUST** be cmtk — pyqtgraph and cmtk are the
only two backends; the wgpu/opengl experiment backends retire. chiplot is
cmtk's **first external consumer**, so PRD-104 Phase 2 breadth (bars, error
bars, regions, pan/zoom, image, log axes) is driven by real chiplot call
sites via a `chisurf/gui/chiplot/backends/cmtk/` package. Long term, cmtk
also replaces PyQt as the UI backend behind the AutoForm seam (web-capable
ChiSurf, drop the PyQt licence). See [PRD-64](../prds/prd-64.md) (Phase 5+
and "Long-term direction").

**Superseded later the same session: `renderer/ui/` is merged into
`cmtk/`.** The paragraph above reasoned that a repo-wide rename of an
already-shipped, pervasively-imported package was out of scope for this PRD
and kept the two packages separate, with `ui/` as the precedent `cmtk`
followed. The user overrode that directly: *"all chimol widgets and autoform
must be in cmtk"*. Scoped by a clarifying question (AutoForm is a
chisurf-wide, 170-file, 75-plugin-directory framework at `chisurf/gui/autoform/`
that predates chimol — moving *that package* into a chimol subpackage would
invert the whole app's dependency graph, so the confirmed scope was: merge
`renderer/ui/` into `cmtk/` so chimol has one widget namespace, and
repoint AutoForm's one narrow bridge module (`qt_host.py`) at the merged
package — leaving AutoForm's own location untouched). All thirty files that
were under `renderer/ui/` now live directly in `cmtk/` (no
subdirectory) — `painter.py`, `qt_painter.py`, `quad_painter.py`, `widgets.py`,
`style.py`, `qt_host.py`, `atlas/`, and the rest, alongside `axis.py`,
`markers.py`, `plot.py`, `gizmo.py`. Every import site was updated: 64 files
inside the chimol plugin, plus 5 outside it (`chisurf/gui/autoform/sections/
code_editor_section.py` and `memory_editor_section.py`, `chisurf/plugins/misc/
games/lumis_quest/{api/settings.py,gui/imgui_controls.py}` — lumis quest
reuses chimol's ImGui-style controls directly — and a doc-comment in
`chisurf/core/dataspec/schema.py`), plus the atlas-baking build tool
(`build_tools/bake_chrome_atlas.py`), the widget-porting scaffolder
(`build_tools/dev_utils/port_imgui_widget.py`), the atlas guard test
(`test/test_chrome_atlas.py`), and a chrome benchmark
(`test/benchmarks/benchmark_chimol_chrome.py`). Historical/dated entries in
`okf/log.md` and `okf/plugins/chimol-web.md` were deliberately **not**
rewritten — they describe what was true when written, and `renderer/ui/` was
the real name then.

## Where to pick this up

**2026-08-13 — the gizmo is removed. Read this before touching anything
gizmo-related in the entries below.** User, after the chrome-refinement round
directly below: *"gizmo is ugly as fuck remove. contine with tick."* Removed
outright — `cmtk/gizmo.py` deleted, not kept disabled behind a flag or a
config switch. Every wiring point removed too:

* `chisurf/plugins/chimol/chimol/renderer/internal_gui.py` — `Hit.kind`'s
  `"gizmo"` value, the `_GIZMO_DRAG_THRESHOLD`/`_GIZMO_CHROME_TURN`/
  `_GIZMO_STATE_KEY` module constants, every `on_gizmo_*` callback attribute
  and `_gizmo_*` state field from `__init__`, the `_gizmo_widget_rect`/
  `_gizmo_geometry`/`_gizmo_hit`/`_paint_gizmo`/`_persist_gizmo_position`
  method block (was between `_top_chrome_height` and `_bottom_chrome_height`),
  the `hit_test`/`mouse_press`/`drag`/`release`/`is_dragging`/hover-tooltip
  branches, `layout_info`'s footprint-reservation block (the one that used
  to prevent the info panel/gizmo click collision — gone because there is no
  longer a gizmo to collide with), and the final `_paint_gizmo(p)` call in
  `paint`.
* `chisurf/plugins/chimol/chimol/renderer/canvas_base.py` — the three
  `on_gizmo_orient`/`on_gizmo_rotation`/`on_gizmo_orbit`/`on_gizmo_turn`
  callback assignments in `init_viewport`, right after `InternalGui()` is
  constructed.
* `chisurf/plugins/chimol/chimol/renderer/view.py` — the `on_gizmo_home`
  wiring block (`MolView.__init__`, right before the display-config
  listener registration). `MolView.reset_view` itself is untouched — it
  predates the gizmo and other things call it.
* `chisurf/plugins/chimol/chimol/cmtk/__init__.py` — the `from .gizmo import
  ...` block and every `gizmo_*`/`GIZMO_*` name from `__all__` and
  `CONTROL_MODULES`; the module docstring's "Beyond widgets: plotting and the
  view gizmo" section is now just "Beyond widgets: plotting", with one
  sentence noting the gizmo was tried and removed, pointing here.
* `chisurf/plugins/chimol/test/test_gizmo.py`,
  `chisurf/plugins/chimol/test/gizmo_baseline.py`, and
  `chisurf/plugins/chimol/test/renders/gizmo_baseline/` (the rendered PNGs) —
  all deleted.

Verified after removal: `chimol.cmtk` and `chimol.renderer.internal_gui`
import clean, 3885 tests collect (down from 3946 — the ~59 gizmo tests plus a
handful of others gone with them), a 267-test targeted sweep
(`test_wheel_routing`, `test_internal_gui`, `test_viewport_chrome`,
`test_panel_layout`, `test_dbg_window`, `test_engine_is_portable`,
`test_qt_seam`, `test_cmtk_plot`, `test_painter_triangle`,
`test_quad_painter`, `test_ui_widgets`) passes clean.

**Why the three rounds of work below are kept, not deleted.** This concept's
job is an honest account of what was tried, not a changelog of what shipped —
a future session reaching for a view-navigation gizmo again should be able to
read what was built, what it looked like, and that it was rejected on sight
after real iteration (not abandoned half-built), rather than re-deriving all
of it from nothing. One piece is genuinely reusable on its own terms even
without a gizmo: the generalised orientation-solving math
(`_orientation_for_direction`, any direction → `(elevation, azimuth)` via
`CameraState.reset_view`'s own formula, asserted to reproduce the old
hand-solved 6-axis table exactly) does not exist anywhere else in this tree
and is worth reading from git history rather than re-deriving, should
something else ever need "look at the camera from this direction."

**2026-08-13 — gizmo refinement round, against three reference
screenshots.** The solid ViewCube from earlier the same day (next entry
down) shipped; the user then looked at it against three real
Autodesk/SolidWorks-style ViewCube screenshots and said "no good" about the
closest match, with itemizable gaps. This is a refinement of that design,
not a rebuild — the cube/face/edge/corner/snap/orbit/reposition mechanism
stays exactly as the previous entry describes it.

*What the three references actually showed*, transcribed from full-resolution
inspection (not visible to the implementing agent, which worked from this
transcription): (A) a long, bold axis triad — roughly as prominent as the
cube's own edges, not a small corner accent — plus genuine perspective
distortion on the cube faces; (B) a hover state with chrome *outside* the
cube's silhouette: a home icon (top-left), a pair of curved 90°-roll arrows
(top-right), an outward triangle on each of the panel's 4 edges (nudge
controls), and a dropdown chevron in a filled circle (bottom-right); (C) a
3/4 view confirming the bold axis triad and showing each face's label text
slanted to match that face's own foreshortened plane.

*What landed, six items in priority order:*

1. **Bolder, longer axis triad.** `_AXIS_LINE_WIDTH` 2.2→3.2 (now close to a
   hovered face edge's own width), `_AXIS_OVERSHOOT` 0.55→1.0 (capped there,
   not pushed further — the cube's own top edge abuts the grip strip with no
   gap, so a much longer upward tip reaches into the grip's row). Also fixed
   along the way: the label text is the same colour as its axis line, so a
   longer line reaching a similarly-dark backdrop (the grip strip, or a face
   close in hue) made the letter unreadable — a 1px dark (`_LABEL_COLOUR`)
   halo drawn behind the coloured, bold glyph fixed this generally, not just
   for the case that surfaced it. Found by rendering at `ui_scale=2.0` on a
   500x500 canvas and cropping tight on each tip with PIL — at the shipped
   360x300/`ui_scale=1.0` baseline size the missing label was too small to
   notice by eye.

2. **A small, fixed perspective for the gizmo's own mini-scene**
   (`gizmo._project`), independent of the main viewport's projection — real
   ViewCubes always render themselves with a bit of perspective as a depth
   cue. A virtual camera sits `_GIZMO_CAMERA_DISTANCE = 12.0` cube-half-units
   behind the projection plane; a vertex at `_view`'s own depth `d` scales by
   `12 / (12 - d)`. The 8 corners reach depth ±√3, so the nearest corner
   magnifies ~1.17x and the farthest shrinks to ~0.87x — a ~1.34x ratio,
   checked in `test_perspective_is_modest_not_extreme` against the
   reference's "genuine but not wide-angle" read. `_layout_cube`'s corner
   loop and `_draw_axis_indicator`'s origin/tip both route through
   `_project` now instead of the old bare `_view`; face
   visibility/depth-sort/shading are untouched (they key on `_view`'s own
   unscaled depth component, unaffected by the screen-space perspective
   scale).

3–6. **Chrome added around the cube**, not just inside it —
   `gizmo._chrome_zones`/`hit_test_chrome`/`draw_chrome`, wired into
   `InternalGui._gizmo_hit`/`_paint_gizmo`/`mouse_press`. Every zone sits in
   a band `gizmo.chrome_margin` (30% of cube size, floored) reserves on the
   cube's **left, right and bottom** — deliberately not the top, which is
   already the drag-to-reposition grip strip's row from the previous entry;
   a second control stacked there would either collide with it or duplicate
   its "move things from the top" gesture, so there is no `"nudge-up"` zone
   at all (`test_there_is_no_nudge_up_zone`).
   - **Home** (top-left): a house pictogram in `icons.py`'s own
     `fill_rect`-runs style (`_HOME_GLYPH`, 9 columns matching
     `icons.OPEN_EYE`'s scale) — not a Unicode `🏠`, which the atlas would
     silently fail to bake (`docs/development/chimol_widget_toolkit.md`'s
     "only draw glyphs the atlas has baked"). Fires `InternalGui.on_gizmo_home`
     immediately on press (like the grip, not deferred like a cube
     face/edge/corner press) — wired to `MolView.reset_view` in `view.py`
     (orientation *and* re-framing, PyMOL's own `reset` semantics), not
     `CameraState.set_orientation` alone, because `on_gizmo_home` is wired
     one layer above `canvas_base.CanvasRenderer` (which only has
     `CameraState`, no notion of "what to frame").
   - **Roll arrows** (top-right, two curved arrows + arrowheads, drawn as a
     partial-ring `line()` sweep rather than a hand-authored pixel glyph —
     more legible at this size than pixel art, and this is exactly the kind
     of shape the toolkit's line/triangle primitives already draw well).
     Wired to `CameraState.turn("z", ∓90)`. The sign was **checked
     numerically, not assumed**: `turn("z", +90)` moves a point that
     projects to screen-right to screen-up, which is counter-clockwise, so
     `roll-ccw` → `+90`, `roll-cw` → `-90` (`_GIZMO_CHROME_TURN` in
     `internal_gui.py`, `_draw_roll_arrow`'s docstring in `gizmo.py`).
   - **Edge nudge-triangles** (left/right/bottom only, see above), stepping
     the view 90° — the same increment as the roll arrows, per the task's
     own suggested default. Signs also checked numerically by asking which
     face a `turn` brings into view from a front-on start: `turn("x", +90)`
     brings TOP into view → `nudge-down` is `turn("x", -90)`; `turn("y",
     -90)` brings RIGHT into view → `nudge-right` is `turn("y", -90)`,
     `nudge-left` is `turn("y", +90)`.
   - **Dropdown** (bottom-right, a filled circle + chevron via `disc`/
     `line()`): drawn and hit-tested, deliberately **inert**. Its real menu
     contents (toggle perspective, set-as-home, isometric presets are the
     usual options in other ViewCube implementations) were not identifiable
     from the reference crop alone — rather than invent a submenu, the press
     handler consumes the click (so it does not fall through to orbiting the
     viewport underneath) and does nothing, with the tooltip saying so
     ("more view options (not wired up yet)").

   All four wire through two new `InternalGui` callbacks:
   `on_gizmo_home: () -> None` and `on_gizmo_turn: (axis, angle_deg) -> None`
   — the latter wired verbatim to `CameraState.turn` in
   `canvas_base.CanvasRenderer.__init__` (no adapter needed, the signatures
   already match), the former one layer up in `MolView.__init__` for the
   reason above.

*Not attempted: per-face perspective-slanted label text* (reference C).
`Painter.text` (`cmtk/painter.py`) has no rotation parameter — checked, not
assumed — and adding one is a toolkit-wide change (every backend,
`QtPainter`/`QuadPainter`, plus the atlas) out of scope for a gizmo
refinement; doing it silently as a side effect here was explicitly the wrong
call. Labels stay axis-aligned.

**Footprint grew, on purpose this time.** `InternalGui._gizmo_widget_rect`
now returns a 5-tuple (`wx, wy, cube_size, grip_h, margin`, was 4 without
`margin`) — every call site and test updated. The grip strip now spans the
*whole* widened panel width (`cube_size + 2*margin`), not just the cube's own
width, reading as one title bar over the whole widget rather than a narrower
strip floating above a wider footprint. `layout_info`'s gizmo-footprint
reservation (added in the previous entry to fix a real `test_wheel_routing.py`
regression) was updated to reserve the *new*, wider rectangle — same fix,
carried forward rather than re-derived, and `test_wheel_routing.py` still
passes. A flat translucent `draw_panel` backdrop (`_PANEL_BG`) sits behind
the whole cube+chrome footprint, standing in for the reference's rounded
card + drop shadow — `Painter` has no rounded-rect or shadow primitive and
nothing else needs one, so a flat fill was judged not worth a ninth
operation for one caller.

**Verification.** `test_gizmo.py` grew from 34 to 59 tests: perspective
magnification/modesty/face-visibility-invariance, chrome zone geometry and
hit-testing (every key reachable at its own zone centre, parametrized), the
"no nudge-up" invariant, `draw_chrome`'s hover-gold tinting, and
`InternalGui` wiring for home/roll/nudge (fire immediately on press, `
is_dragging()` stays `False` — unlike a cube face/edge/corner press) and the
dropdown (consumes the click, calls nothing). `gizmo_baseline.py` gained a
fifth capture, `chrome_hover` (three-quarter view, home button hovered),
alongside the existing four — **all 5 PNGs rendered and inspected by hand**,
plus additional `ui_scale=2.0` zoomed captures used only for debugging (not
committed) that caught two real bugs before they shipped: the Y-axis label
landing inside the grip strip's row and blending into its own line (fixed by
item 1's halo), and a hovered home/roll/nudge icon drawn in the *same* gold
as its own hover background — invisible, gold-on-gold — fixed by giving the
icon a dark colour specifically when its own zone is hovered
(`draw_chrome`'s `icon_colour` closure) rather than reusing `GOLD` for both.
Broader sweep re-run and green: `test_wheel_routing.py`, `test_internal_gui.py`,
`test_viewport_chrome.py`, `test_chrome_atlas.py`/`test_chrome_cache.py`/
`test_chrome_scale_and_paging.py`/`test_chrome_frame_cost.py`,
`test_sequence_chains_and_labels.py`, `test_cmtk_plot.py`, `test_dbg_window.py`,
`test_selection_markers.py`, `test_mouse_selection.py`, `test_browser_render.py`,
`test_engine_is_portable.py`. One unrelated, pre-existing failure was observed
and deliberately **not** touched: `test_chrome_painter.py`'s 5
byte-identical-PNG checks fail against the currently-checked-out
`renders/chrome_baseline/*.png`, but those states never wire
`on_gizmo_rotation` (the gizmo is not drawn in them at all, confirmed by
reading `chrome_baseline.py`), so the failure predates and is unrelated to
this refinement; the PNGs were already modified (`git status` showed `MM`)
before this session's gizmo work started, i.e. they are another instance's
in-flight, uncommitted change per the shared-working-tree convention, not
this one's to fix or recapture.

**Open.** The dropdown's real behaviour is still unknown — a future session
with a clearer reference (or a product decision) should replace the inert
placeholder. Per-face slanted labels need `Painter.text` rotation, a
separate, larger toolkit change. The zoom/pan corner buttons and the eased
snap animation remain unported (unchanged from every earlier entry).

**2026-08-13 — the gizmo redesigned: from six axis balls to a solid
ViewCube.** Every dated entry below this one, back through "Phase 4 landed",
describes the **six-axis-ball** gizmo (`ImViewGuizmo.h` ported faithfully) —
accurate when written, and **now superseded**: the user showed a reference
screenshot and said "make the gimbal like that", which turned out to be the
classic Blender/3ds Max/ChimeraX ViewCube the reference header itself said
this port was *not*. `cmtk/gizmo.py` was rewritten outright (not kept behind
a flag); every mention below of balls, spokes, a centre disc, or
`AXIS_ORIENTATIONS` as a hand-solved six-entry table describes code that no
longer exists. Read this entry, not those, for the current design.

**What it is now.** A cube, corners at `(+-1,+-1,+-1)`, projected the same
way the axis balls were (`_view`: one matrix-vector product against
`CameraState._rotation`, generalised from 6 axis directions to 8 corners --
each is just a sum of signed axes, and a rotation is linear). Up to 3 of 6
faces are visible at once (normal's projected depth > 0), drawn
back-to-front as two `fill_triangle`s each, pale-gray shaded (darker at a
grazing angle), with a darker outline and a centred label (`TOP`/`FRONT`/...)
skipped once the face foreshortens past a dot-product threshold (no room for
readable text). A small red/green/blue X/Y/Z axis indicator extends from the
nearest visible corner, reusing the axis-ball design's own colour table and
signed label scheme (`X`/`-X`/`Y`/`-Y`/...) unchanged.

**Orientation snapping, generalised.** The axis-ball design solved
`(elevation, azimuth)` for each of 6 signed axes **by hand**, from
`CameraState.reset_view`'s own rotation formula (row 2 = pivot-to-camera
direction), and kept the 6 pairs as a literal table (`AXIS_ORIENTATIONS`) --
kept verbatim, now purely as a regression target. `_orientation_for_direction`
solves the *same* equation for any direction (`el = asin(vy)`, `az =
atan2(vx, vz)`, with the `+-Y` gimbal handled the same way the old table
did), and a test asserts it reproduces all 6 old values exactly. The other 20
snap targets fall out of the same function for free: an edge's direction is
the normalised sum of its 2 adjacent faces' directions, a corner's the sum of
its 3 -- 26 orientations (6 faces + 12 edges + 8 corners) from one function
instead of a hand-solved table.

**Hit-testing, and why the order is corner -> edge -> face, not the
reverse.** A corner and an edge are not regions *beside* their face -- each
sits exactly on the face's own polygon boundary, so testing the face first
(the "biggest target wins" instinct) would let its point-in-quad test claim
every corner and edge pixel, making the smaller, more specific targets
unreachable except at an exact mathematical boundary. Corner (small circular
zone) and edge (thin capsule band) are tested first; the face is the
catch-all for whatever neither claims. Returns `"face:<name>"` /
`"edge:<name>"` / `"corner:<name>"` (e.g. `"corner:right-top-front"`),
resolved to an orientation via `orientation_for_key`.

**Interaction model: press-then-release snaps, press-then-drag orbits.** The
standard ViewCube split (Blender/3ds Max/ChimeraX all do this), replacing the
old "handle vs. big invisible disc" split that stopped making sense once the
cube is solid and covers most of the footprint. A press on the cube
(face/edge/corner, anywhere) is held pending in `InternalGui._gizmo_pressed`;
`drag()` checks the accumulated distance from the press point against
`_GIZMO_DRAG_THRESHOLD = 6.0px` (matching `cmtk.dragdrop`'s own click-vs-drag
threshold, the closest existing precedent for "did the pointer actually
move") and, once exceeded, promotes to `_gizmo_orbiting` and calls
`on_gizmo_orbit` for the accumulated delta, continuing frame-by-frame after
that exactly like a viewport drag. Short of the threshold, `release()` snaps
via whatever `_hover` says at that moment (unchanged from the axis-ball
design's own "read live hover at release" logic).

**The widget is now draggable, separately from the cube.** A small
title-bar-style grip strip sits above the cube (`cmtk.gizmo.draw_grip`/
`grip_height` -- a plain filled strip with three dots, the same "grab here"
affordance a scrollbar thumb uses). Chosen over a modifier-key-held drag or
overloading the cube's own drag because it needs a trigger that cannot be
confused with orbiting the cube face itself, and a strip is the same
convention a `GuiWindow`'s own title bar already uses in this chrome. The
**total footprint stays exactly the size-ball design's own footprint**
(`cmtk.GIZMO_SIZE * ui_scale`, unchanged) -- the grip strip is fit *inside*
that budget by shrinking the cube slightly, not added on top of it. That
turned out to matter: growing the footprint downward by the grip's own height
regressed `test_wheel_routing.py` (a click meant for the info panel, three
rows into a `help` listing, landed on the gizmo instead), because the info
panel's own top-left corner (`top_band_height() + MARGIN`) already sits
almost exactly where the gizmo's does -- the two have shared that corner by
coincidence since the axis-ball design, invisible only because six small
balls rarely covered the exact pixel a click landed on. Fixed at the root
either way: `layout_info` now reserves the gizmo's *current* footprint
(`_gizmo_widget_rect`, which already tracks a dragged position) the same way
it already reserves the toolbar/sequence strip via `top_band_height()`, so a
long listing no longer grows under a widget drawn on top of it, and dragging
the gizmo elsewhere gives the space back automatically.

**Position persists the way a `GuiWindow`'s does, without being one.** No
title bar, no resize, no close button -- so it does not go through
`InternalGui.windows`/`persist_windows`. Instead its `(x, y)` is written into
the *same* `chimol_windows.json` under a reserved key
(`_GIZMO_STATE_KEY = "__view_gizmo__"`), reusing `window_state.py`'s
`load_states`/`save_states` directly rather than inventing a second
mechanism — the established pattern for "a chrome element remembers where the
user put it" in this codebase. `reset_windows()` (the "put a bad layout
back" escape hatch) clears it too.

**A `Painter`-level bug this surfaced, fixed at the root.** The first
renders showed a visible diagonal line bisecting every filled face — a face
is two `fill_triangle` calls sharing a diagonal, and `qt_painter.py`'s
`fill_triangle` filled with `NoPen`, so two independently antialiased paths
meeting at a shared edge do not reliably sum to full coverage there (a classic
T-junction crack). Not a gizmo-specific fix: `qt_painter.QtPainter.fill_triangle`
now strokes with a hairline pen in the fill's own colour, which closes the
crack and is invisible on a triangle's own outer boundary (same colour
either way). This changed pixels for anything using `fill_triangle` app-wide
(icons, `line()`, plot markers), so `chrome_baseline.py`'s committed PNGs
were re-captured — and that recapture also picked up an unrelated, already
pre-existing staleness (`test_chrome_painter.py` was failing before this
session's changes too: the committed baselines predated the "the object
list's eye is drawn" fix a few commits earlier and were never re-captured
for it). Both are one fix, verified: `test_painter_triangle.py` and
`test_quad_painter.py` still pass (no vertex-count/shape assertions broke),
and `test_chrome_painter.py`'s 8 byte-identical-PNG tests pass again.

**Verification.** `test_gizmo.py` rewritten for the cube (34 tests: cube
topology invariants, the orientation solver against the regression table,
layout/hit-test/draw geometry, and the full `InternalGui` press/drag/release
wiring including the reposition drag and its persistence).
`gizmo_baseline.py` re-targeted at 4 orientations (front square-on, a
three-quarter view showing all 3 axis colours and 3 face labels at once, an
axis-on view, and a close corner view with a hovered gold highlight ring) —
**all 4 PNGs rendered and inspected by hand**: faces read as a pale, flat-shaded
cube with legible labels where there is room for them, edges are thin and
darker, the axis indicator's three colours and letters are legible without
dominating the cube, and the corner hover highlight is visible. Broader sweep
also run and green: `test_internal_gui.py`, `test_viewport_chrome.py`,
`test_wheel_routing.py`, `test_sequence_chains_and_labels.py`,
`test_chrome_atlas.py`/`test_chrome_cache.py`/`test_chrome_scale_and_paging.py`/
`test_chrome_frame_cost.py`, `test_cmtk_plot.py`, `test_dbg_window.py`,
`test_selection_markers.py`, `test_mouse_selection.py`,
`test_browser_render.py`, `test_engine_is_portable.py`.

**Open.** The zoom/pan corner buttons and the eased snap animation are still
not ported (same as the axis-ball design, `CHISURF-SKIPPED` in the reference
header) — chimol's viewport already has wheel-zoom/pan, and an instant snap
was a deliberate choice, not an oversight, but nobody has revisited whether
an eased snap is worth adding now that the target reads as a real object
rather than a ball. The gizmo/info-panel corner-sharing is mitigated (the
panel yields), not redesigned — a future session touching either should be
aware they still occupy the same nominal corner.

**2026-08-13 — nerd panel is fixed-width now.** User: *"the nerd stats view
must be fixed width and not vary, assert enough space."*
`InternalGui._paint_nerd` sized the block to `max(len(line) for line in
self.nerd_lines) + 2` — content-dependent, so the panel visibly resized
frame to frame as e.g. the pipeline list or object counts changed length.
Replaced with a constant, `InternalGui.NERD_WIDTH_CHARS = 68`, clipped
(`push_clip`/`pop_clip` around the text loop) so anything that does not fit
is cut rather than grown around. The "assert enough space" half:
`test_nerd_lines_fit_the_fixed_width` stresses `FrameStats.lines()` with the
widest plausible values per field (a five-name pipeline list, three-digit
millisecond figures, a real long GPU adapter string, a six-digit instance
count) and fails if any line would spill past the box. **Caught its own first
guess**: `62` failed against a genuine long adapter name ("AMD Radeon Pro
W7900 Dual Slot Workstation Edition (Metal)", 64 chars) — the assertion is
what makes that a test failure instead of a silent clip nobody would notice.
43/43 `test_dbg_window.py` pass; re-rendered the nerd-mode screenshot and
looked at it.

**2026-08-13 — a second look at the gizmo: spokes still hard to see, discs
pixelated.** User followed up with a screenshot after the size/hit-test fix
above. Reproduced their exact orientation (elevation 0°, azimuth 90° — solved
from what was on screen: Y straight up, Z straight left, X collapsed onto the
centre, which only that orientation produces) at a clean render size, zoomed
in, and confirmed both by eye:

* **The spokes were real but thin** — 2.5px against a ~19px ball reads as a
  hairline next to a disc. `gizmo.py` gained a named `_SPOKE_WIDTH = 4.0`
  (was an inline literal) and the primary-handle `line()` call now uses it.
  Widened, not brightened — the fade-factor alpha mixing already carries
  depth information a flat opacity bump would fight.
* **The pixelation is real but is not this widget's bug.** The visible
  horizontal banding in every ball is `style.disc()`'s band-rasterised
  circle — `bands = clamp(round(radius), 3, 24)`, hard-edged horizontal
  strips, no anti-aliasing — and it is the **same primitive every rounded
  control in the toolkit uses**, not something specific to the gizmo. Fixing
  it means either raising the band count (more `fill_rect` calls per disc,
  paid by every checkbox/radio/colour-picker in the app, not just the
  gizmo) or adding real anti-aliasing (a materially bigger change to the
  painter). **Deliberately not done here**: the user's very next message in
  the same round was "the ui is really laggy, diagnose why" — increasing
  per-disc draw calls app-wide while that investigation is open would be
  moving in exactly the wrong direction on unverified guesswork, the same
  mistake `frame_stats.py`'s own module docstring warns against ("it feels
  slow is not a measurement"). Revisit once the laggy-UI diagnosis has an
  answer and a performance budget to spend against.

Re-verified: `test_gizmo.py` (22/22), `gizmo_baseline.py`'s three PNGs
re-rendered and looked at again.

**2026-08-13 — relocated: `chimol.renderer.cmtk` → `chimol.cmtk`.** User:
*"cmtk should be on another module level: chimol.cmtk instead of
chimol.renderer.cmtk."* Package physically moved up one directory
(`chisurf/plugins/chimol/chimol/renderer/cmtk/` →
`chisurf/plugins/chimol/chimol/cmtk/`), a bigger mechanical job than the
`ui/`→`cmtk/` merge earlier the same session because this one changes
**directory depth**, not just a name — every relative import's dot-count
needed recomputing per importing file, not a blind find/replace. Two shapes
the first-pass script missed, both real import errors caught by actually
importing the package afterward (not just grepping):

* `internal_gui.py`'s `from . import cmtk` (a bare module import, not
  `from .cmtk import X`) — the regex patterns only matched dotted forms.
  Now `from .. import cmtk`.
* Six files moved from the old `ui/` package (`command_line.py`,
  `memory_editor.py`, `inputs.py`, `text_field.py`, `text_editor.py`) reach
  `chimol/host/` via a relative import **inside a function body** —
  `grep -n "^from"` (anchored to line start) missed every one of them because
  they're indented. `from ...host.X import Y` (three dots, correct at the
  old `renderer/cmtk/` depth) is one dot too many now that the package sits
  one level higher; all became `from ..host.X import Y`.

Absolute references (170+ across the repo — chimol source, tests, docs, OKF,
`build_tools/`, and the two same outside-chimol consumers as before) fixed by
dropping `.renderer`/`renderer/` before `cmtk`. Two segmented-`pathlib`-literal
traps repeated from the `ui/`→`cmtk/` merge (`"chimol" / "renderer" / "cmtk"`
as separate path segments, invisible to a `renderer/cmtk` string search) in
`test_chrome_atlas.py` and `bake_chrome_atlas.py` — same category of bug,
found the same way, by grepping for the bare segmented literal specifically
rather than trusting the string-search sweep alone. Verified: 3907 tests
collect, 754 directly-relevant tests pass, all outside-chimol consumers
(AutoForm's two bridge sections, lumis_quest, `dataspec/schema.py`) import
clean.

**2026-08-13 — feedback round: the plots were choppy, the gizmo was unusable.**
Two direct reports, both fixed:

* **"Make the plots run smooth, base tick at 100 ms."** `frame_stats.REPORT_INTERVAL`
  was 0.5 s — the nerd-mode line plots only re-fit and redraw on that cadence,
  so at 60 fps the plotted line jumped by up to 30 samples in one visible
  step every publish. Now `0.1` (`frame_stats.py`): five times the redraw
  rate, still nowhere near every frame (which is what the chrome-cache-cost
  concern the module docstring already explains is protecting against —
  `_publish_nerd`'s cost is an opt-in debug feature, off by default, so a 10 Hz
  chrome-invalidation cost when a developer has explicitly turned nerd mode on
  is an acceptable trade). `_FPS_REPORT_INTERVAL` (`canvas_base.py`, the plain
  numeric fps *readout*, not a plot) was deliberately left at 0.5 s — a number
  redrawn ten times a second is unreadable, the module's own comment already
  says so, and the user asked about "the plots", not the counter.
* **"gimbel thing is ugly and too small also why can't I click on the
  diagonals?"** Two real defects in `cmtk/gizmo.py`, from a
  screenshot showing it cramped against the menu bar in a small window:
  1. **Too small to click.** The reference's own proportions
     (`_HANDLE_RADIUS_RATIO` 15/128 ≈ 0.117 of the half-size) are a ~5px
     radius ball at the old `DEFAULT_SIZE` of 84 — a target a pointer misses
     more often than it hits. `DEFAULT_SIZE` → `120.0`, `_HANDLE_RADIUS_RATIO`
     → `0.16`. Diverges from the reference's literal ratios deliberately: a
     faithful port of proportions that read as broken here is not a virtue.
  2. **The diagonal spoke itself was not clickable** — only the tiny ball at
     its tip was, per the reference. `hit_test` now also accepts a click
     anywhere along a primary handle's spoke (point-to-segment distance,
     `_dist_to_segment_sq`, same capsule width as the ball). **First attempt
     was wrong and caught by testing before shipping it**: gating the spoke
     test on "past the centre-disc radius" (`big_r`) turned out to disable it
     almost everywhere, because a spoke's own length
     (`half * _LINE_LENGTH`) is *shorter* than `big_r` at these ratios — the
     whole visible spoke sits inside the orbit-drag disc by design. Caught by
     checking a spoke's own midpoint, which returned `"orbit"` instead of the
     axis. Fixed by gating on the much smaller `handle_r` instead (excludes
     only the literal convergence point where every spoke starts, not the
     spoke's whole length) — verified the midpoint now resolves to the axis
     *and* that a couple of pixels off dead-centre at a tilted rotation (no
     axis facing the camera, so nothing collapses onto the centre the way
     +Z/-Z do at identity) still resolves to `"orbit"`. Two new tests
     (`test_hit_test_lands_on_a_spoke_not_just_its_tip`,
     `test_hit_test_near_the_exact_centre_is_orbit_not_a_spoke`) pin both
     halves.
  3. **Not fixed, deliberately**: the screenshot's window was ~154×146px, in
     which even the *old* 84px gizmo nearly fills the height — `DEFAULT_SIZE`
     is fixed regardless of viewport by design (`okf/prds/prd-101.md`'s
     browser-chrome-scaling bug is the precedent for not repeating that), and
     a genuinely tiny window is not this component's problem to solve. At the
     1280×860 default viewport the new size reads comfortably; verified with
     a realistic render carrying a populated menu bar + toolbar (`gizmo_baseline.py`'s
     existing screenshots never populated either, which is *why* the real
     overlap-with-the-menu impression in the report was never caught — the
     geometry itself (`_gizmo_geometry`) turned out to be correct, an 8px
     margin below `_top_chrome_height()` with no literal overlap; the
     "cramped" read was the small window, not a geometry bug).

**2026-08-13 — Phase 4 landed: the view gizmo, clickable and wired to the camera.**
`cmtk/gizmo.py` ports `Ka1serM/ImViewGuizmo`'s `Rotate`. First
correction worth stating up front: **the reference is not a cube.** It has no
faces, edges or corners — it is six axis balls (`+X`/`-X`/`+Y`/`-Y`/`+Z`/`-Z`)
plus a big, mostly-invisible centre disc that starts an orbit drag. The PRD's
own Phase 4 description ("projected quads... flat/Lambert shading... cube
reads as 3-D") was written before the reference was actually opened and has
been corrected in place (see PRD-104's Phase 4 paragraph) — what shipped is
what the reference has, not a cube invented to match the PRD's guess. Reading
item 5 below is corrected for the same reason.

Geometry (`_view`, `_layout`, `hit_test`, `draw`) needs no GUI toolkit and no
4x4 matrices: the reference's `gizmoViewMatrix` applied to a world axis
vector is, for chimol's convention, exactly `CameraState._rotation @ axis` —
see `_view`'s docstring in `gizmo.py` for the row-by-row derivation (row 2 of
`_rotation` is the pivot-to-camera direction, which is what makes the
`AXIS_ORIENTATIONS` snap table a closed-form six-entry lookup rather than
something solved at runtime). Depth from that same product both sorts the six
handles back-to-front (painter's-algorithm overdraw — there is no z-buffer
behind `Painter`) and fades the far side, matching the reference's
`mix(fadeFactor, 1.0, (depth+1)*0.5)`.

Wiring, file:line at time of landing:

* `InternalGui.__init__` (`internal_gui.py`, next to `on_playback_change`) —
  three new callback attributes: `on_gizmo_orient(elevation, azimuth)`,
  `on_gizmo_rotation() -> np.ndarray` (a getter — the gizmo asks what the
  camera is doing *this frame*, there is no cached copy), `on_gizmo_orbit(last,
  cur)`. `canvas_base.py`'s `init_viewport`, right after `InternalGui()` is
  constructed, assigns `self.set_orientation` / `lambda: self._rotation` /
  `self.orbit` — `self` there is the `CameraState` mixin.
* `Hit` gained a `"gizmo"` kind (`key` is `"axis0"`..`"axis5"` or `"orbit"`).
  `InternalGui.hit_test` tests it early (`_gizmo_hit`, right after the
  toolbar, before the floating windows) so it stays always-on-top; `_gizmo_geometry`
  (right after `_top_chrome_height`) is the single source of the gizmo's
  centre/size and returns `None` — no gizmo, no hit, no paint — whenever
  `on_gizmo_rotation` is unset, which is every existing test's bare
  `InternalGui()` and is why none of them needed touching.
* `mouse_press`/`drag`/`release`/`is_dragging` gained a `hit.kind == "gizmo"`
  branch each, following the exact shape the splitter/timeline/ui-scale drags
  already use (no new dispatch mechanism). A handle press does **not** start
  a drag of its own — it sets `_gizmo_pressed` and `drag()` just keeps
  `_hover` live; `release()` reads whatever `_hover` says *then* and snaps if
  it is still an axis, which is what makes "press a handle, drag off it,
  release" correctly **not** snap (reference behaviour, tested in
  `test_gizmo.py`). The centre disc instead sets `_gizmo_orbiting` and calls
  `on_gizmo_orbit` every `drag()`.
* Position: top-left, below the menubar/toolbar/sequence-strip band
  (`_top_chrome_height()`), sized by `self.MARGIN`/`self.ui_scale` — the two
  corners a Blender-family gizmo usually claims are both taken already
  (`objects_window` anchors top-right, the mouse block bottom-right).
  Deliberately **not** scaled by viewport size — see the `_gizmo_geometry`
  docstring's pointer to the browser-chrome-scaling defect this does not
  repeat.

Verification: `test/test_gizmo.py`, 20 tests — geometry (identity-rotation
handle positions, back-to-front sort, the `depth < -0.1` skip-when-facing-away
hit-test guard), the `AXIS_ORIENTATIONS` table round-tripped through
`CameraState.reset_view`'s own rotation formula, `draw()` against
`RecordingPainter` (label visibility, hover ring, orbit-disc-only-on-hover),
and the full `InternalGui` press/drag/release flow for both gestures,
including the "drifted off the handle" no-snap case. `test/gizmo_baseline.py`
renders three headless PNGs (front / three-quarter / straight-down-Y) through
the same `gui_overlay.paint_chrome` path `chrome_baseline.py` uses, saved
under `test/renders/gizmo_baseline/`. **Inspected by hand, all three plus an
ad hoc fourth (hovering the `-X` handle):** X/Y/Z read in their reference
colours (red/green/blue) with the axis facing the camera correctly collapsing
to the gizmo's centre and the opposite axis correctly hidden behind it;
negative handles are dim and unlabelled until hovered, at which point the
label appears and a gold ring lights up around the handle; the three-quarter
view shows genuine depth variation across all six handles and, in the state
captured, the translucent centre-disc hover fill; nothing overlaps the object
list or mouse-block windows at 360x300. `Dolly`/`Pan` (the reference's
zoom/pan corner buttons) and the eased snap animation were **not** ported —
chimol's viewport already has wheel-zoom and drag-pan, and an instant
`set_orientation` cut reads fine; both are noted as `CHISURF-SKIPPED` in the
reference header, and are natural small follow-ups if the instant snap ever
reads as jarring.

Ran (not just the new file): `test_painter_triangle.py`, `test_ui_widgets.py`
(unaffected), plus a broader offscreen sweep of ~19 internal_gui/canvas-facing
files (~390 tests, 10 pre-existing failures — see below). All green.

**Two pre-existing failure clusters hit during the broad sweep, confirmed not
mine:** (1) `test_camera_framing.py::test_a_widget_that_was_never_laid_out_frames_square`
— a `RecursionError` inside `canvas_base.py`'s own `_draw`/`_draw_frame` pair,
reproduced identically with this session's `canvas_base.py` callback-wiring
lines removed, so it predates this change entirely. (2) `test_chrome_painter.py`'s
five byte-identical PNG-baseline states and 4 of `test_wheel_routing.py`'s 24
checks — the committed `chrome_baseline` PNGs were last recaptured at commit
`f02941b2e`, before `69e65a927` ("nerd mode graphs the frame") and later
commits already on `HEAD` touched `internal_gui.py`; the gizmo draws nothing
at all for any of these states (`on_gizmo_rotation` is unset in bare
`InternalGui()`, so `_gizmo_geometry` returns `None` and `_paint_gizmo` is a
no-op), so this is a stale baseline unrelated to any of today's work, gizmo or
plotting. Worth a `chrome_baseline` re-capture in its own change, not fixed
here.

`junk/ImViewGuizmo/ImViewGuizmo.h` carries its `CHISURF-REVIEWED`/`-TAKEN`/
`-SKIPPED`/`-RECORD` header now.

**2026-08-13 — Phase 1 landed: cmtk draws the nerd-mode frame-stats graphs.**
`chisurf/plugins/chimol/chimol/cmtk/` now has `axis.py` (`Axis`,
`nice_ticks` -- Heckbert's algorithm), `markers.py` (circle/square/diamond/
cross), `plot.py` (`Plot`, `begin_plot`; ImPlot's default "Deep" categorical
palette, `implot.cpp:509`, as `DEEP_PALETTE`). 16 tests in
`test/test_cmtk_plot.py`, all passing (`RecordingPainter`, no GUI toolkit).

**The first production caller is `InternalGui._paint_nerd_graph`**
(`renderer/internal_gui.py`), not a standalone demo — a demo would have
proven the plotting code works; wiring the real "nerd mode" readout proves it
replaces something. The four non-stacked series (fps, frame time, cpu load,
gpu-submitted instances) now draw as real `cmtk.begin_plot` line plots with
`y_range=(0.0, None)` (baseline pinned at zero, ceiling auto-fit — matches
the old bars' scale) and `Plot.hline` for the 60/30 fps and 16.7/33.3 ms
reference lines (previously `_paint_nerd_guides`, drawn peak-relative; now
just another item, clipped by the plot's own `push_clip` when a guide falls
outside the fitted range — no more `if 0 < value <= peak` special case). The
stacked "frame time, in detail" breakdown graph is **unchanged** — still bars,
via a `_paint_nerd_guides` that now has exactly one caller left. Series carry
no label (`plot.line("", ...)`): the row's caption above the plot already
names it, and a legend swatch would cover more of a 26px-tall graph than it
explains.

Headless-rendered and inspected (`gui_overlay.paint_chrome`, the same path
`chrome_baseline.py` uses) with synthetic data across all five graphs: the
line traces are real diagonals, not stair-steps, correctly auto-fit and
correctly showing/clipping their guide lines. One **pre-existing, not
introduced here** cosmetic defect seen in the same screenshot: the stacked
breakdown row's caption ("frame time, in detail") and its right-aligned
"latest value" string (`scene 8.7  chrome 7.5  wait 1.4`) can overlap when
both are long — `_paint_nerd_graph` draws them with plain `ALIGN_LEFT`/
`ALIGN_RIGHT` and no `style.fit_text` truncation, unchanged from before this
PRD. Worth fixing, not fixed here (out of this PRD's scope — it predates the
plotting port entirely).

Full suite re-run clean except 5 pre-existing `test_chrome_painter.py` PNG-
byte-diff failures (`panel`, `panel_and_sequence`, `menu_open`,
`movie_transport`, `command_line`) — confirmed unrelated: `git diff` on the
painter files touched by Phase 0 shows zero overlap with the `fill_rect`/
`stroke_rect`/`text` code paths those baselines exercise, and none of those
five states render the nerd overlay at all.

**2026-08-13 — foundation phase in progress.** User asked to port
[epezent/implot](https://github.com/epezent/implot) and
[brenocq/implot3d](https://github.com/brenocq/implot3d) into chimol's UI
toolkit as `tk`/`cmtk`, then to also add
[Ka1serM/ImViewGuizmo](https://github.com/Ka1serM/ImViewGuizmo). All three are
now mined into `junk/implot`, `junk/implot3d`, `junk/ImViewGuizmo`
(`junk/clone.sh`, "chimol in-viewport plotting/gizmo toolkit" section) —
combined ~21.7k lines of reference C++ (implot 12,587; implot3d 8,473;
ImViewGuizmo 630).

This is not a task that finishes in one session. What follows is the honest
state, phase by phase, so the next session does not re-derive it.

* **The floor was axis-aligned rects only, by design** — see
  [chimol-viewport-ui.md](chimol-viewport-ui.md) and
  [`docs/development/chimol_widget_toolkit.md`](../../docs/development/chimol_widget_toolkit.md)'s
  "What is not here, and why". `PlotLines` (`cmtk/widgets.py:1001`)
  already substitutes a staircase-of-columns for a true polyline, and says
  explicitly this only holds "at sparkline sizes". None of ImPlot's line
  plots, scatter markers, or ImPlot3D's meshes are expressible that way at
  plot-area size, so PRD-104 adds one primitive (`fill_triangle`) rather than
  faking it with more rectangles.
* **Two existing `Painter` backends must both gain it and stay in parity**:
  `qt_painter.py` (the reference — `QPainterPath`) and `quad_painter.py` (the
  GPU one — a second raw-triangle vertex list alongside the existing
  rect-corner expansion, since `vertices()`'s corner math is derived from
  `x, y, w, h` and has no slot for three independent corners). `RecordingPainter`
  in `test/test_ui_widgets.py` needs the same method so control tests keep
  needing no GUI toolkit.
* **`junk/imgui` was already present** before this PRD (a prior chimol widget
  port used it) — useful cross-reference for implot/implot3d since both are
  extensions of the same author's Dear ImGui immediate-mode conventions
  (`ImVec2`, per-frame context, `Begin`/`End` pairing).

### Reading order for whoever continues this

1. `junk/implot/implot.h` — the public API surface (`BeginPlot`/`EndPlot`,
   `SetupAxis`, `PlotLine`, `PlotScatter`) is what `cmtk`'s call shape should
   track, adapted to a Python context manager since there is no destructor to
   lean on for the implicit `EndPlot`.
2. `junk/implot/implot_internal.h` — `ImPlotAxis`, `ImPlotPlot`, the
   pixel↔plot transform (`PixelsToPlot`/`PlotToPixels`) that every plot type
   shares; port this once, correctly, before any plot type, or every plot type
   re-derives its own (and disagrees under zoom/pan).
3. `junk/implot/implot_items.cpp` — one function per plot type; each is a
   template over the data-getter, which Python has no need to mirror (just
   accept a sequence).
4. `junk/implot3d/implot3d_internal.h` then `implot3d_meshes.cpp` — the 3-D
   analog of (2), plus the primitive meshes (sphere/cube/cylinder/cone) as
   worked examples of "how does a triangle list become a `fill_triangle` call
   sequence".
5. `junk/ImViewGuizmo/ImViewGuizmo.h` — small enough to read start to finish.
   **Not a cube**: `Rotate` lays out six axis balls plus a centre orbit-disc,
   no faces/edges/corners at all (see the Phase 4 resume note above, and
   PRD-104's corrected Phase 4 paragraph) — landed as `cmtk/gizmo.py`.
   The part worth transcribing carefully is the depth-based fade/sort and the
   primary-vs-secondary handle distinction; the projection itself is a single
   matrix-vector product once you have `CameraState._rotation`.

### Phase status

- **Phase 0 (foundation): done this session** if the commit that follows this
  note lands `fill_triangle`/`line` on both painters with a passing parity
  test — check `git log` for a commit touching `painter.py`, `qt_painter.py`,
  `quad_painter.py` referencing PRD-104 before trusting this line.
- **Phase 1 (cmtk 2D MVP):** see PRD-104's Definition of Done for the checked
  state. If unchecked, `chisurf/plugins/chimol/chimol/cmtk/` does not
  exist yet or is incomplete — start from implot_internal.h's axis transform
  (item 2 above), not from a plot type, or the transform gets rebuilt per
  plot type and disagrees under zoom.
- **Phase 2 (2D breadth), Phase 3 (cmtk3d):** see PRD-104. Neither blocks on
  the other, or ever blocked on Phase 4.
- **Phase 4 (gizmo): done.** See the "2026-08-13 — Phase 4 landed" resume note
  above and PRD-104's Definition of Done.

### junk/ annotation debt

Only the files actually read carry a `CHISURF-REVIEWED`/`CHISURF-SURVEYED`
header (see [reference-checkouts.md](../workflows/reference-checkouts.md)).
Check `python -m build_tools.dev_utils.reference_coverage junk/implot
junk/implot3d junk/ImViewGuizmo` for the current count rather than assuming
full coverage — a large fraction of implot/implot3d (the demo files, the
`example/` backends) is deliberately never worth reading and should be
surveyed `D` rather than skipped silently.

## See also

* [PRD-104](../prds/prd-104.md) — full scope, phases, definition of done.
* [ChiMOL — one UI, drawn in the viewport](chimol-viewport-ui.md) — the
  painter and control conventions this extends.
