---
title: ChiMOL — one UI, drawn in the viewport
status: in-progress
group: plugins
updated: 2026-08-12
---

# ChiMOL — one UI, drawn in the viewport

## Where to pick this up

**2026-08-13 — the chrome gained a code editor and a hex view, and porting is
now tooled.** How a control family gets into `renderer/ui/`, the scaffolder that
does the mechanical third, the shared recording painter and the Qt host that
puts any control in an AutoForm section are all in
[Porting a widget into chimol's chrome](../subsystems/chimol-ui-ports.md).
Read that before adding a seventeenth family.


**2026-08-12 — the performance objective now has a named baseline and a PRD:
[PRD-102](../prds/prd-102.md).** tpeulen: **YASARA's performance is the baseline
chimol has to match**, tested with a *gigastructure*, plus support for **pet
molecules** and the ability to **assemble** gigastructures in chimol through
IMP. The numbers to design against, from YASARA's own pages: a presynaptic
bouton of **3.6 billion atoms**, interactive on a single **RTX 2080**, reached
by two independent compressions — coarse-graining **~50x** and GPU instancing
**40-1000x**. Neither alone is enough, which is the whole design: 50x off 3.6e9
is still 72 million. Read PRD-102 before starting; the rest of this entry is
the same objective stated earlier.

chimol must handle systems **up to 30x the size of the NPC**. Speed is the
objective, not a nice-to-have, and loading the NPC demo is still slow today —
that demo is the benchmark to beat.

The approach tpeulen named, and the one to try first: the NPC is **many copies
of the same molecule type**, so exploit that rather than treating every copy as
unique geometry — **clones/instancing plus the hierarchy**. One built mesh per
distinct type, drawn N times with per-instance transforms, instead of N built
meshes. That collapses build time *and* VRAM by the copy count, which is the
only kind of factor that reaches 30x.

Read **ChimeraX** (`junk/ChimeraX`) for how a molecular viewer does this at
scale before designing anything — it is already the reference this plugin used
for density-map contouring, and its headers there record what was taken.

Do not re-derive: the NPC+RMF unified load has already gone **430 s / 11 GB →
2 s / 0.7 GB** (see the RMF/voxel work). The open items from that round —
interior culling, dynamic LOD, fog — are the ones that matter for the 30x
target.


**2026-08-12 — Qt is to be an option, not the default.** tpeulen: *"make it
possible to run chimol without qt. qt should be just an option, the default
(running of module) should work without qt"*, and *"chimol uses no Qt except
the embedding window"*.

The architecture already allows this and most of the work is deletion, not
design: `host/widget.py` makes `MolView` a plain object when there is no
toolkit, `host/events.py` is a toolkit-free event vocabulary, and the browser
*already* runs the real `MolView` with the real `cmd` layer and no Qt at all.
What is missing is a desktop host that is not a `QWidget`.

**The audit, so it is not re-derived.** `test_engine_is_portable.py`'s `HOSTS`
is the tracker — a shrinking list of modules allowed to import Qt at module
scope. It stood at 14 and is **stale by two**: `app/hierarchy_panel.py` no
longer exists and `app/volume_panel.py` no longer imports Qt, so
`test_the_host_list_is_not_padded` is red on the tree until they are struck.

Of the rest, only two are the embedding window — `app/molview_main_window.py`
and `renderer/wgpu_view.py`. Everything else is removable, and in three
different ways:

1. **Four vestigial widgets, kept alive as state holders.** `controls_panel`,
   `objects_panel`, `rmf_panel`, `sequence_dock` are constructed and then never
   shown; the source says so itself — *"nothing puts it on screen"*, *"Built but
   not docked: the strip in the viewport replaced its tab"*. About **50 call
   sites** still read them (`self.sequence` 22, `self.controls` 12,
   `self.objects` 12, `self.rmf_panel` 4), mostly for things like
   `button_info.isChecked()`.

   **The pattern to follow already exists and is proven**: `volume_panel` became
   `VolumeViewModel`, a pure-Python model, and dropped out of `HOSTS` on its
   own. Do the same four times. This is the bulk of the job and it is
   mechanical.
2. **Redundant copies of in-viewport panels.** `app/settings_table.py` is the
   Qt settings table the derived settings window replaced; it is still reachable
   from a `QAction`. `renderer/gui_overlay.py` (355 lines) is the legacy
   `QPainter` chrome rasteriser that `QuadPainter` superseded, still called from
   `wgpu_view` for `paint_chrome` / `refresh_gui_state` / `image_from_rgb`.
3. **Dialogs — and "no dialog left" is not yet true.** Commit `edefb7d26` says
   it, and the *config* dialog is indeed gone, but `demos.ScriptEditor` is a
   live `QDialog` and there are four `QFileDialog` / `QInputDialog` call sites
   (`app/menu_bar.py`, `app/demos.py`, `app/objects_panel.py`,
   `io/structure.py`). A native file picker is defensible; a script editor is
   the kind of panel the chrome now draws.

`app/timeline_panel.py` has **zero** references anywhere and is simply dead.

**The one thing that is genuinely missing**, rather than merely redundant: a
desktop window that is not Qt. `rendercanvas` 2.7.2 is a dependency and ships
`glfw`, `offscreen`, `qt`, `wx`, `jupyter` and `raw` backends — but the `glfw`
**pip package is not installed**, so today only `offscreen` is available and a
Qt-free run renders without a window. Declaring `glfw` in `pixi.toml` /
`pyproject.toml` is what turns the default into a real interactive window.

---

**2026-08-12 — the Dear ImGui widget stack is ported.** `renderer/ui/` went
from one control module to fourteen: the nineteen controls in `widgets.py`
plus `text`, `buttons`, `sliders`, `drag`, `inputs`, `color`, `selection`,
`menus`, `tabs`, `tables`, `dragdrop`, `layout` and the shared `style`. One
module per section of the reference's `imgui_widgets.cpp`, so a control can be
read against the source it came from. ~14,100 lines, 494 painter-level tests.

The idiom did **not** change, and that is the load-bearing decision: a control
is still a retained object with `draw(p, x, y, w, h)` / `press(x, y, box_*)` /
`drag` / `release`, drawn through the six `Painter` operations. The reference
is immediate-mode around a per-frame global; chimol is immediate-mode in
*style* and retained in *implementation*. Where the reference reads that
global for something chimol has no feed for — hover, a clock, a modifier, a
click count — the port takes it as an **explicit argument** (`press(...,
ctrl=, shift=)`, `hover(x, y, now)`). No second paradigm was introduced.

What is left, in the order it is worth doing:

1. **Nothing consumes the new controls yet.** They are tested and photographed
   but no panel is built from them. The two obvious first customers are named
   below (`density_window`, `settings_editor`), and the ported `menus.py`
   could replace ~250 lines of inline menu code in `internal_gui.py` — see
   *Re-pointing the hosts* below for what each costs.
2. **`widgets.Table` and `widgets.Tabs` are now the lesser of two.**
   `tables.DataTable` and `tabs.TabBar` are strict supersets. Neither old one
   should be deleted casually — `Table` has callers, `Tabs` has none outside
   its own tests — but new code should not reach for them.
3. **Four things were deliberately not ported.** `Image`/`ImageButton` and the
   colour **wheel** are not expressible in six axis-aligned operations and were
   left out rather than faked. **Box-Select** updates by differencing against
   the *previous frame's* band, which a retained model has nothing to
   difference against; a snapshot-at-drag-start equivalent is a different
   algorithm and was not smuggled in under the same name. Nav/keyboard,
   docking and `.ini` persistence belong to the global context chimol does not
   have. All four are recorded in the `junk/imgui` headers.

### The trap this port paid for: Qt cannot see a missing glyph

The Qt painter draws with a **font**; the GPU painter draws from the **baked
chrome atlas**. A character the atlas lacks therefore looks perfect in every
screenshot and paints as *nothing* in the app. Four ported controls hit it —
the tab bar drew `✕` and `◂`, the table drew `▲` and `✓`, none baked.

The fifth was **already shipped and unnoticed**: `widgets.Table`'s ascending
sort mark was `▲` and its descending mark `▼`, and only `▼` is in the atlas —
so sorting a column ascending in the GPU chrome showed no marker at all while
descending showed one. That asymmetry is exactly the shape this bug takes, and
no assertion and no Qt screenshot could see it.

All five now spell symbols the atlas has (`▴`/`▾`, `◀`/`▶`, `■`, ASCII), and
`test_chrome_atlas.py` grew a parametrised guard over **every** module in
`renderer/ui/`. The atlas's non-ASCII set is `… ─ ■ ▴ ▶ ▸ ▼ ▾ ◀`; widening it
costs texture area the chrome uploads on every repaint, so the fix is to spell
the symbol with a baked glyph, not to bake another. The same test also stopped
reading raw source characters — it counted a *comment* naming `×` as something
drawn, which punished writing down the very warning that prevents the bug.

### Looking at them: `test/widget_gallery.py`

`QT_QPA_PLATFORM=offscreen python -m chisurf.plugins.chimol.test.widget_gallery`
writes one PNG per family to `test/renders/widget_gallery/`. It is a
development tool, not a test — there is no golden image, the point is that
somebody reads it. Three defects were found only by reading it and are the
argument for keeping it: a colour editor whose `label` was accepted and never
painted, a vertical slider whose caption was drawn *inside* the frame and
covered by the grab at minimum, and the glyph problem above.

### Re-pointing the hosts (measured, not guessed)

* **`density_window.py` → `layout.Layout`**: the clear win. Its `_ROW/_GAP/_PAD`
  constants *are* a `LayoutStyle`, and its `_draw_*` helpers each take a `y`
  and return the next one — precisely what the cursor removes. ~30–40
  mechanical edits across five methods; low risk because `press()` reads
  recorded rects and those would now come from `row()` unchanged. The header
  row's right-aligned overlays are `same_line(offset)`, whose rule differs from
  `same_line()` — that is the part to get right.
* **`settings_editor.py` → only partly.** Its list divides a fixed body height
  by `visible_rows` rather than accumulating row heights — the inverse of a
  cursor, and correct as it is. Only the band arithmetic around it is worth
  moving (~10 lines). Its label/control split is a **weighted** two-column
  split, which `columns(n)` deliberately does not do; that needs a
  `SetColumnWidth` port first.
* **`internal_gui.py` → `menus.py`** would delete roughly 250 lines, but four
  gaps must close first: `Menu` needs scrolling/paging (the panel already has
  it, ~60 lines), `MenuItem` has nowhere to put `note`/`prompt`/`colour`, there
  is no `entry_at(x, y)` for the wheel handler, and the wizard's dynamic
  submenus build children at open time.

## Where this was picked up before

**As of 2026-08-11 the migration itself is done** — the 3-D view is the window's
only widget and every panel is drawn by the renderer. What is left is the work
tpeulen deferred behind it (*"just note as issues and continue with migration.
after done with 3d view as mainwindow tackle issues"*), in the order it was
reported:

0. **The chrome's size is one setting now — keep it that way.**
   `internal_gui_scale` (`layout.ui_scale`, default 0.85) scales text *and*
   rows: `InternalGui.set_ui_scale` multiplies `SCALED_LENGTHS` onto the
   instance, `char_width(font_pt)` scales the baked advance, and
   `QuadPainter(font_scale=…)` scales the glyph quads. A new hard-coded length
   in `internal_gui.py` is a length that stops following the knob — add it to
   `SCALED_LENGTHS` in the same change. The trap already paid for: the two
   halves must be given the *same* number, or the boxes and the text in them
   disagree, and `FONT_PT` therefore stays fractional where every other length
   rounds.

0. **A settings panel is not a settings *system*.** The panel derives its rows
   from the configuration, so a setting with no declared range gets a guessed
   track (zero to twice its value) — honest, and useless to drag. `RANGES`
   covers the common suffixes; the rest are guesses until somebody who knows
   what a setting means writes it down. The other half is the same gap the
   parity tracker calls the standout one: only ~85 of the 270 rows are
   *registered* settings with a name and a line of documentation, and the rest
   show as their dotted path.
1. **Voxel mode is wrong and density has no colour/alpha controls.** (The
   sliders and swatches this asked for now exist in `renderer/ui/widgets.py`.)
   The voxel
   style draws `Geometry(kind="points")` — screen-space dots that keep their
   size as the camera moves; tpeulen: *"voxel must be size of grid not hollow
   points"*. A voxel has to be a **box of `grid.step`** in scene units, which
   also changes the budget (250 000 boxes is three million triangles, and the
   point cloud is capped at 250 000 today). Read `junk/` first — ChimeraX's own
   solid mode is ray-cast volume rendering with a **transfer function**, which
   is where the requested colour and alpha controls come from, so the two are
   one design. The widgets are ImGui's `ColorEdit4` and `SliderFloat`, and
   `renderer/ui/` has neither a slider nor a colour swatch yet — both are
   reusable, so they belong there rather than inside `density_window.py`.
2. **Density maps are "super slow"**, with the instruction to *learn from
   ChimeraX how to do it right*. Recorded with the ChimeraX guidance in
   [known-issues](../references/known-issues.md). The measurement to re-derive
   first: time one contour rebuild at the map's native step, then at step 2 and
   step 4 — ChimeraX picks the step from the voxel count and re-contours the
   *displayed region* only. The trap is that the drag already defers its rebuild
   to `release()` (`renderer/density_window.py`), so a naive "the drag is smooth
   now" reading says the problem is fixed when the single rebuild is still the
   cost.
3. **Loading the NPC regressed** and takes far longer than it did. Not the same
   bug as the hierarchy flatten (that one is fixed and measured); this is the
   load path itself, and it needs a before/after against a commit that predates
   the regression rather than a guess at which stage is slow.
4. **The rendering defects** listed below — surface and metaball torn, `ray` too
   dark, `show as ribbon` dead, `cell` wrong, dots not scaling with zoom.
5. **`2f5n`'s cartoon has spikes.** Ribbons run off to infinity, and they do it
   with `2f5n` loaded **alone** — `148L` alone is clean, so the repro is one
   structure and the difference is that `2f5n` is protein *plus DNA* over
   several chains. A cartoon spline crossing a chain break is exactly this
   shape; check `_build_trace_ups` / `_residue_chain_ids` before anything else.
   This is the half of *"fetch on top of another breaks the geometry"* that the
   shared-scene-frame fix did **not** address.
6. **Selections do not work in the browser**, and there is no `.wrl` / `.glb` /
   `.stl` export. `.glb` is the one with a stated purpose — PowerPoint imports
   it.
7. **The unreproduced water bug** (hidden waters reappearing after a colour
   change). Ten command variants and both load paths did not reproduce it;
   it needs tpeulen's actual command sequence, and until then it is not a lead.

---

The direction, stated by tpeulen on 2026-08-11: **every relevant interface
lives in the viewport, drawn by the renderer — menus included** — so the same
code serves PyQt and the browser. The Qt docks around the 3-D view are to go.
The style reference is **Dear ImGui** (`junk/imgui`, vendored source): its
*look and its in-view draggable windows*, ported to plain Python drawing
through the existing `Painter` seam. Not a binding — chimol already has the
engine for this.

Why this is credible rather than a rewrite: `InternalGui` is **already** a
toolkit-free layout + hit-test engine that paints through six operations
(`chimol/renderer/ui/painter.py`) and rasterises as GPU quads
(`ui/quad_painter.py`). The object list, sequence strip, mouse-mode block,
wizard panel, menus and the command prompt are all drawn that way today. The
system-info panel was the last Qt widget stacked on the surface and was ported
on 2026-08-11 — that port is the worked example to follow.

**What is missing for the rest is a *window*:** a draggable, resizable,
titled, collapsible frame that other panels live inside, plus a z-order and a
"which window has the pointer" rule. That is the one new mechanism; everything
after it is moving existing panels into one.

### The order to build in

1. ~~**A window frame in `InternalGui`**~~ — **DONE 2026-08-11.** `GuiWindow`
   plus `add_window` / `window` / `raise_window` / `remove_window`,
   `layout_windows`, `_window_hit`, `_press_window`, `_drag_window`,
   `_paint_windows`. Title bar, move, corner resize, collapse (button *and*
   double-click), close, z-order-raises-on-click, clamped into the viewport.
   `gui.draw_windows = False` takes them out of a frame, and `png` wraps its
   framebuffer grab in `_windows_hidden`; `ray` renders the scene through the
   tracer and never saw chrome at all.

   **Contents go in through `GuiWindow.body`**, a `(painter, rect)` callback,
   so the frame knows nothing about density contours or hierarchies — that is
   the seam the next four steps hang off. `lines` is the no-callback case.

   Two things worth not re-deriving: the grab reach for the resize corner is
   **4 px outside** it (ImGui's `WindowBorderHoverPadding`) because a
   one-pixel edge is not a mouse target; and windows are clamped inside the
   viewport because there is no window manager underneath to retrieve one
   dragged off the edge.
2. **The density/contour controls** move into it, and the Qt Map dock goes.
   These are also reported **slow and prone to getting stuck while dragging a
   threshold**, so the port is the moment to fix the recompute path: a contour
   drag must not rebuild the isosurface synchronously per mouse move.
3. ~~**Hierarchy** into a window~~ — **DONE 2026-08-11**, including the three
   defects reported against the first cut: a draggable **scroll bar**; the
   **search box drawn before the tree is looked up** (it was drawn after, so a
   structure with no `rmf_hierarchy` — i.e. every PDB — showed one sentence and
   no field, which is why "the filter does not work"); and the **flatten
   cached and the tree shut below depth 1** (327 ms per repaint → 0.0005 ms on
   a 200 000-node pore). A structure without an RMF tree now gets one
   synthesised from its atom table, object → chain → residue.
4. ~~**The Command and Objects docks**~~ — **DONE 2026-08-11**, and then all of
   them: `setCentralWidget(self.viewer)`, no `DockArea`, no toolbar, no Qt menu
   bar, no Qt hierarchy dock. The 3-D view **is** the window.

   Two traps: a `QToolBar` parented to a `QMainWindow` is re-shown by Qt's own
   layout the moment the window is, so `hide()` is not enough — `setParent(None)`
   is; and the Qt menu bar drew a **second copy of the viewport's menus directly
   above them**, which no assertion could see and the first grab showed at once.
5. ~~**Menus in the viewport**~~ — **DONE 2026-08-11**; `app/menu_bar.py`'s
   `MENU_BAR` table now feeds `InternalGui.layout_menubar`, and the Qt bar it
   also feeds is no longer installed.
6. ~~**Settings in the viewport**~~, and ~~**the last Qt dialog**~~ —
   **DONE 2026-08-12**. `app/config_editor.py` is deleted; `config` is an
   alias for `settings_panel`. Menus taller than the viewport are **paged**
   (`menu_pages` / `page_menu` / `_menu_page_button`), not only scrolled, and the Qt settings
   table is now the redundant copy rather than the only editor.
   `renderer/settings_window.py` + `Display → Settings` / `settings_panel`.

   The part worth not re-deriving is *why the rows are derived*. A panel with a
   hand-written row per setting shows the settings somebody remembered — and
   the ones it omits are exactly the new ones. So `build_model()` walks the
   live `_DISPLAY_CONFIG` (270 rows across 28 sections today), takes the PyMOL
   name and the documentation from a registered `SettingSpec` where one exists,
   and addresses registered settings **by name** so their stored/shown
   transforms run (`transparency` edits as transparency, is kept as
   `surface.alpha`). What cannot be derived is the slider track: `RANGES` gives
   it by key *suffix*, so one rule covers every `*_radius`.

   Three things the first screenshot caught that no assertion did: a **tab
   strip cannot carry 28 sections** (each pill was narrower than one letter —
   it is a `Combo` now); a label wider than its column is drawn **over** the
   control beside it, since the painter clips nothing (`widgets.fit_text`); and
   a scrollbar is not optional when a section has 63 rows.

### The web viewport's scale

Reported 2026-08-11: in the browser the chrome **scales with the viewport**, so
it becomes unreadable when the canvas is small. The chrome is laid out in
logical pixels and scaled by device-pixel ratio on the desktop side
(`_ratio()`); the browser path must do the same rather than scaling the whole
overlay to fit. Chrome should be a **constant apparent size** and the scene
should take the rest.

## Rendering defects reported alongside it (2026-08-11)

Each is separable from the UI work and none is diagnosed yet beyond what is
written here.

* **Surface representation is broken**, and **metaball with it** — both come
  out as torn shards of triangles rather than a closed skin (two screenshots).
  Suspected the Gaussian-splat path they share. The user's instruction is
  explicit: **use the next slower variant for surfaces** rather than the splat.
* **Mesh looks identical to surface.** In PyMOL `mesh` is a *wireframe* of the
  same isosurface — check `RepMesh` before changing anything.
* **Density maps need three display modes: surface, mesh and voxel.** Voxel is
  missing entirely.
* **A volume map that has been unloaded still draws.** Clear the volume state on
  unload — it is showing content from a map that is no longer loaded.
* **`ray` output is too dark** against what the live view shows (screenshot).
* **`show as ribbon` does nothing.** And **`trace` should come out of the menu**:
  in PyMOL a *ribbon* is the backbone trace, so the two entries are one thing —
  confirm against PyMOL's `RepRibbon` before removing the entry.
* **`cell` draws wrongly** — the box is not around the molecule (screenshot).
* **Dots do not scale with zoom.** Their size looks wrong as the camera moves;
  `dots.px_mode` is the flag to check, and it is the same "flag read by nothing"
  shape as the pixel-size defect already recorded for the point glyph.

## Done, 2026-08-11

**C ▸ by element** is PyMOL's, at last: `cnc` (H/N/O/S by element, **carbon
untouched**), `cba <carbon>` and `cbh <hydrogen>` are commands, and the submenu
is PyMOL's **49** entries rather than one. The old leaf issued
`color byelement` — a colour *mode*, which is a property of an **object**, so
selecting a side chain repainted the whole protein and cleared every per-atom
override on the way. Measured: `cnc resi 20-25` now changes exactly the 19
non-carbon atoms of those residues and nothing else.

**A measurement trap worth keeping:** `set_atom_color_override` seeds its array
from the object's *current* colours, so after any colour command every atom has
an entry. Counting entries therefore says "all of them" and proves nothing —
diff the colours before and after instead. That mis-measurement briefly looked
like a second bug.
