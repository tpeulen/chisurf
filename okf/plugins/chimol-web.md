---
type: Plugin Concept
title: ChiMOL in the browser — one WGSL codebase
description: ChiMOL must also run in a web page embedded via JavaScript. WebGPU is the only graphics+compute API spanning macOS desktop, Linux/Windows and the browser, so desktop and web share one WGSL source.
resource: chisurf/plugins/chimol/
tags: [plugins, structure, viewer, webgpu, wgsl, web, pyodide, compute]
timestamp: '2026-08-10T00:00:00Z'
---

# One code path — the page runs the viewer (2026-08-11, latest)

**The browser runs `MolView` and `Cmd`.** Not a browser viewer and a browser
command set: *the* viewer and *the* hundred-odd commands, with a windowless
renderer whose scene the page rasterises. `load`, `as cartoon`, `as spheres`,
`as sticks`, `select`, `bg_color`, `count_atoms` — all of them, in a page,
because they are the same code.

**What made it possible, and it is small.** `MolView` is the object store, the
scene builder, the camera and everything `cmd/` drives (sixty-seven of its
methods); being a `QWidget` was incidental to all of it and was the only reason
a page could not import it. `host/widget.py` supplies the three things it needs
from a toolkit — a base class, four signals, a timer — and stand-ins when there
is none. `view.py`'s Qt import is now guarded, and its widget-construction block
was already guarded on the renderer *being* a widget (since `SceneSink`).
**`renderer/view.py` has left `HOSTS`: 16 → 15**, and the viewer is an engine
module in `test_engine_is_portable.py`.

**Deleted with it:** `web/commands.py` (a parallel command set) and `demo.py`'s
own scene builders — `build_molecule`, `build_cartoon`, `_occlusion*`,
`_chain_segments`. `web/demo.py` is now a *host*: a canvas, DOM events, and the
thirteen application calls the commands make (`BrowserHost`).

**Three imports stood between the page and the viewer, and each was a one-liner
with a large consequence:**
- `cmd/loader.py` imported `ssl` at module scope. Pyodide ships `ssl` as a
  *loadable package*, so the whole command layer failed to import in a page with
  a message about ssl. Now local to `_tls_context`.
- `fetch` called `urllib.request.urlopen` directly, which cannot open a socket
  in a tab. `host/net.py` is the seam — `pyodide.http.open_url` in a page,
  `urllib` elsewhere — so `fetch` stays one command.
- **scipy.** `geometry/__init__` imports `neighbors`, `ambient` and `surface`,
  and all three imported scipy at module scope, so a page paid a ~14 MB download
  to *import the viewer*. Gone: see below.

## scipy is out of the engine

`geometry/grid_pairs.py` is a vectorised uniform grid — sort points by cell,
answer all 27 neighbour cells with `searchsorted`, no Python loop over points
and no compiler. `neighbors.py`, `ambient.py` and `surface.py` route through it;
`surface.py` also gained `_edt_numpy`, the parabola-envelope distance transform,
which reproduces `scipy.ndimage.distance_transform_edt` **exactly** (checked on
1-D, 2-D and 3-D random masks).

**The measurement, and it is not flattering.** Pair sets are *identical* to
`cKDTree`'s, and the grid is **5–8× slower**:

| n | radius | pairs | grid | cKDTree |
|---|---|---|---|---|
| 1,363 | 4 Å | 8,209 | 12 ms | 2.5 ms |
| 20,000 | 4 Å | 122,094 | 323 ms | 39 ms |
| 50,000 | 3 Å | 131,774 | 874 ms | 127 ms |

A grid inspects ~6× more candidates than it returns pairs — that is the shape of
a 3×3×3 stencil against a sphere — and the bookkeeping across 27 offsets, not
the distance test, is where the time goes (making the candidate gather
contiguous and float32 moved 14 → 12 ms and nothing at 20k). At scene-rebuild
sizes this is invisible; at tens of thousands of atoms it is the thing to fix,
and **the fix is the GPU kernel the user asked for**, with this as its CPU twin
and its small-input fallback. `grid_occupancy()` reports cells and the fullest
cell, which is how a degenerate case is seen rather than guessed at.

## Next, in this order

1. **The neighbour count on the GPU.** The numbers above are the case for it and
   `renderer/compute.py` already has the router, the seam and `bvh.wgsl`'s prefix
   sum to copy. The shape that wins is one dispatch doing grid, count and the
   integral it feeds without a round-trip between them — measured at
   `CHIMOL_COMPUTE=gpu`, the existing occlusion integral is 806 ms against
   numpy's 39 ms on 1363 atoms, so a kernel that only counts loses by *more* at
   that size. It wins at tens of thousands.
2. **The `app/` panels into the chrome** — thirteen of `HOSTS`' fifteen. Start
   with `sequence_dock.py`, whose replacement already ships.
3. **The page's renderer is still its own.** `web/demo.py` packs the sink's scene
   and calls `render_into`; `wgpu_view.py` does the same thing with Qt around it.
   That is the last real duplication, and it closes by making the Qt widget a
   thin host over a shared frame builder.

# Where to pick this up (2026-08-11, superseded by the section above)

**Landed since the handover below: the browser can be typed at.** chimol has
two command lines now, PyMOL's split: an *internal* one drawn in the viewport by
the engine, and the *external* docked console. Both run the same command layer,
so a browser -- which has no console to dock -- has a real prompt.

- `renderer/ui/command_line.py` is the model (buffer, caret, history, tab
  completion, a feedback log). No toolkit, no GPU, no host: it draws nothing.
- `host/keys.py` states the key values (Qt's) and translates
  `KeyboardEvent.key`, exactly as `host/events.py` does for buttons.
- `InternalGui` lays it out along the bottom of the scene, paints it as quads,
  hit-tests it, and routes keys through `key_press`.
- Hosts: `wgpu_view.keyPressEvent` offers keys to the chrome *first*;
  `boot.js` listens on `window` and calls `Viewer.key`.
- `web/commands.py` is the browser's command set (`bg_color`, `turn`, `zoom`,
  `set seq_view`, …), bound to the browser viewer. **It is a stand-in with a
  known end**: the real `Cmd` acts on a `MolViewPluginWindow`, so it becomes
  reachable when the `app/` panels move into the chrome, and this module is then
  deleted rather than translated.

**The focus rule is the part to not "simplify".** The viewport binds bare
letters (`r`, `c`, `b`, `s`, `d`) to actions, so a prompt that took every
keystroke would disable them with no error and nothing on screen to say why.
Keys reach the prompt only when it is focused -- a click, or Return over the
scene -- and Escape gives focus back. The unfocused line says so.

**Found and fixed on the way:** `wgpu_view.grab_image(chrome=True)` did not pass
`chrome=` to the renderer, so **every headless grab had come back with the
molecule and no panel** since the quads landed -- the chrome moved from
`overlay=` (an image) to `chrome=` (quads) and this call site was not moved with
it. Also a duplicated `sele` row in the browser demo's panel.

**The baselines.** `test/chrome_baseline.py` gained a fifth state,
`command_line`; the four frozen ones switch the prompt *off* explicitly, so
their PNGs stay byte-identical -- they photograph a QPainter chrome that cannot
be re-taken. `inventory.json` gained one key and changed nothing else.

**Selections work without Qt, and the marker is a marker again.**
`renderer/markers.py` is the engine module: PyMOL's width rule
(`ExecutiveGetAdjustedSelectionWidth`), the indicator geometry, and the
column→residue→atom mapping that a strip selection needs. `view.py` keeps only
"which atoms are selected"; the browser calls the same three functions, and
`web/commands.py` gained `select resi 20-40`.

**The scattered-dots report was two bugs, and neither was `px_mode`.** The
handover said the WGSL backend ignores `meta["px_mode"]` and gives pixel markers
world-radius behaviour. It does ignore the flag, but *pixel mode is the
default* — `impostor.wgsl` converts a pixel size to a view extent whenever
`world_radius` is false, so the size was right all along. What was wrong:

1. **No glyph.** `meta["glyph"] = "selection"` was set by the builder and read by
   nobody, so markers went through the *impostor* pipeline and each one was a
   shaded pink **sphere**. `wgsl/marker.wgsl` is the glyph — three concentric
   screen-space squares, unlit — and `pipeline_for` routes to it.
2. **Three pixels cannot show three bands.** At PyMOL's `selection_width` floor
   of 3 the white core is a fifth of a pixel, so every marker resolved to one
   speck. The band is now 7–16 (`chimol_display.json`, the built-in defaults in
   `config.py`, and **migration 14**, or the change reaches nobody who already
   has a profile).

Verified by photographing `select sele, resi 20-40` typed into the viewport
prompt of the real window: 162 markers, square, with visible cores.

## Next, in this order
2. **scipy is on the browser's critical path.** `geometry/neighbors.py` is four
   `cKDTree` calls, and `geometry/surface.py` adds `scipy.ndimage`'s distance
   transform; `analysis/{hbonds,surface_area,symmetry}` and `cmd/measurements`
   each import `cKDTree` lazily. Pyodide ships scipy, but it is a large download
   to draw a molecule, and the user's instruction is to move that compute to the
   GPU. The router in `renderer/compute.py` already picks by size and
   `shade_from_atoms` already has a GPU path — so this is per-primitive work
   behind one module, not a rewrite.
3. **The `app/` panels into the chrome** — thirteen of `HOSTS`' sixteen entries.
   Start with `sequence_dock.py`, whose replacement already ships.

# The OpenGL renderer is gone (2026-08-10)

`renderer/qtgl.py` (2,932 lines) and `renderer/postprocess.py` (452) are
deleted. chimol draws with WGSL and nothing else; a machine with no WebGPU
adapter gets `SceneSink`, which builds scenes and rasterises nothing — honest
about having no window rather than opening an empty one, and logged.

**What had to move first, because deleting a file does not delete what only
lived in it:**

- the mouse-mode helpers (`normalize_mouse_mode`, `rotation_delta_multiplier`,
  `pan_delta_multiplier`) → `mouse_modes.py`, beside the table they describe;
- `_image_from_rgb` → `gui_overlay.image_from_rgb`, and it now **copies**: a
  QImage over a numpy buffer is a view, and the array is routinely a temporary.

**What the deletion cost, and the decision about it.** `capture_gl_baseline.py`
photographed the reference the WGSL renderer is judged against, and its renderer
no longer exists — so the 22 baselines are now **frozen and unrecoverable**. The
script is kept rather than deleted: `SCENES`, `RESET` and `missing_resets` stay
live (that guard is what caught five contaminated baselines), `compare_wgsl`
still replays each scene against the frozen images, and `main()` is replaced by
a message saying why there is nothing to run. Those PNGs are the only evidence
of what chimol looked like under OpenGL.

**Tests that only existed to compare the two backends were repointed, not
deleted** — `test_headless_scene` compares `SceneSink` against the *WebGPU*
widget now, which is the same question (does scene assembly depend on having a
window?) asked of the renderer that draws.

Found on the way and fixed where it lives: **chitable's search box raised on any
table with a vector column.** `_stringify` called `arr.astype(str)`, which
cannot format an object cell holding a list — a colour like `[0, 0, 0, 1]` — so
typing one character into the settings filter raised `ValueError: setting an
array element with a sequence`, naming neither the column nor the row. Nothing
to do with this port; it just had never been searched.

# WGSL is chimol's default renderer (2026-08-10)

`renderer.backend` defaults to `wgpu`, so the viewport is
`renderer/wgpu_view.py::WgpuRenderer` unless `CHIMOL_RENDERER=opengl` says
otherwise -- and automatically when a machine has no WebGPU adapter, which is
logged rather than silent.

**Flipping the default is what found the rest of the gap.** With OpenGL in
front, every hole in the WGSL path was invisible; the moment it became the
default, 31 tests failed and each one named something real:

- **clipping** was entirely absent (`configure_camera` was a no-op), so `clip`
  and shift+wheel did nothing;
- **`origin` was inert** -- `set_origin` stored the pivot without moving the one
  the camera orbits or absorbing the difference into the view offset, so the
  camera kept turning about the old point;
- **`set_lighting` accepted anything**, including typos, and its three
  silhouette values went into a private dict instead of the config both
  renderers read;
- **backgrounds stayed strings**, so `bg_color white` reached the clear as `'k'`;
- **`lighting_state` was an attribute** where the contract is a method;
- the **mouse-mode table** was not consulted at all: box select, ctrl-left pan
  and ctrl-shift-middle pivot were unreachable, and the block on screen
  advertised gestures nothing started;
- the **traced frame** had nowhere to go, and `ray` could not show its result;
- the **ground grid** was configured and never drawn.

All of that is ported, and the camera half of it lives in
`renderer/camera_state.py` where both non-GL backends share it. Two of the
tests were themselves measuring the OpenGL widget's accidental geometry rather
than the framing rule -- an unshown `QOpenGLWidget` reports 100x30, so the
aspect guard read "no window" and the portrait correction never ran; they now
construct the case they claim to cover.

**Also landed:** 3-D labels (`kind == "text"`, painted into the composited
chrome), the depth-outline **silhouette** as a second WGSL pass sampling the
depth buffer, and **atom picking** through `project_to_screen` -- which required
teaching `view_matrix` about the camera-space shift it had been dropping.

**The panel's pop-up menus and wizard work too** — the press carries Qt's
double-click flag (the panel opens menus on `DblClk`, and dropping the flag
leaves every menu unreachable while single clicks keep working, so the panel
looks alive and inert), an open menu owns the pointer, and the wheel scrolls a
menu or the sequence strip before it reaches the camera. Verified by opening the
Action menu and photographing it.

# chimol runs on WGSL (2026-08-10)

`CHIMOL_RENDERER=wgpu python -m chisurf.plugins.chimol` opens the real
application window with `renderer/wgpu_view.py::WgpuRenderer` as its viewport:
the molecule, the object panel, the sequence strip and the mouse-mode block, all
drawn through the WGSL in `renderer/wgsl/`, on Metal. Verified by screenshot
across cartoon / sticks / lines / spheres / surface / transparency, and the
camera it reports for `orient` is the OpenGL baseline's camera to seven figures
(`0.4264863 … −1380.95644`). It falls back to the OpenGL renderer when there is
no adapter — a window with nothing in it is worse than the old backend.

**The window and the baseline comparison are one code path.** `render_into` is
what both call; `render` is a thin offscreen wrapper that allocates a target and
reads it back. That is deliberate and load-bearing: a picture verified against
the GL baseline is *the* picture the window shows, where two paths that merely
"do the same thing" drift — as three constants in this port already did.

**Everything a renderer holds rather than draws is in
`renderer/camera_state.py`**, shared by `SceneSink` and the widget, so a
headless replay and a window frame the same scene identically. PyMOL's
trackball moved there too, and `qtgl` now delegates to it: two viewers whose
drags turn the molecule by different amounts are two different programs, and no
screenshot comparison catches it because every individual frame is correct.

**Not there yet at the time:** picking, the silhouette post-pass and 3-D labels
— all three landed with the default flip above.

# HANDOVER — start here (2026-08-11)

**Where this stands.** The desktop port is **done**: chimol draws with WGSL and
the OpenGL renderer is deleted (`76df2fcfd`). Everything below is what is left,
in the order the user asked for it. The browser half — the whole point of using
WebGPU — has not been started.

**Environment.** The `arm64` conda env, with
`PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:."`.
`wgpu` 0.32.0 and `rendercanvas` 2.7.2 are declared in `pixi.toml` /
`pyproject.toml` (the chigame agent added them).

**The two commands you need.**

```
# the molecule, against the frozen OpenGL baselines
QT_QPA_PLATFORM=offscreen python -m chisurf.plugins.chimol.test.compare_wgsl \
    cartoon sticks surface transparency

# the real window, which is the only thing that shows the chrome
PYTHONPATH=... python -m chisurf.plugins.chimol      # needs a window server
```

**The baselines are frozen and cannot be re-taken.** `qtgl.py` is gone, so the
22 PNGs in `test/renders/gl_baseline/` are the only evidence of what chimol
looked like under OpenGL. `compare_wgsl` still replays each scene's commands and
camera against them, which makes them a **regression reference**: a row that
stops matching is a question, not a failure. `capture_gl_baseline.py` keeps
`SCENES`, `RESET` and `missing_resets` for that reason and refuses to run.

**USER RULES, all learned the hard way here:**
1. **Always produce PNGs.** Never report a rendering result as an IoU, a mean
   brightness or a table of RGB values. Four times now a scalar pointed the
   wrong way and the picture settled it in seconds — most sharply when a
   lit-pixel IoU read **1.000** for a frame that was plainly wrong, because a
   white background counts as lit. Send images with `SendUserFile`.
2. **The WGSL look is the target, not the baseline.** Parity means *feature
   inventory* — every representation, setting and cue present and controllable
   — not pixel agreement.
3. **Flip the switch to find the gap.** A parallel implementation that is not
   the default is not tested, however green its own suite is. Making WGSL the
   default turned 31 silent holes into 31 named failures in one run; nothing
   else had surfaced any of them.

## Do these next, in order

1. **The first render of a large scene, which still pays 241 ms of BVH build.**
   Everything else in this item is done and is here as the context for that one
   number: numba is gone from chimol (`test/test_no_numba.py`'s `ALLOWED` set is
   **empty**), every data-parallel kernel is WGSL compute, and the surface
   pipeline — distance grid → threshold → distance transform → marching cubes —
   passes a `GpuVolume` from one kernel to the next instead of copying an 8 MB
   grid out and back in between each pair.

   **The BVH build is the CPU-side bottleneck of a large trace, and the honest
   state of it is: measured, partly improved, and not finished.** On a *real*
   traced solvent surface — 85,092 triangles, 640×480 ssaa2 — the build is
   **241 ms of a 345 ms render, 70 %**. That is the number to design against; a
   synthetic triangle soup at 320×240 understates it.

   Two fixes were tried and measured:

   - the per-level `lexsort` → a **spatial-midpoint split with a `cumsum`
     partition**, O(n) instead of O(n log n) per level: **no difference.** The
     sort was not where the time went;
   - three `(n, 3)` float64 gathers per level → **one packed `(n, 12)` float32
     gather** (upper bound and upper centroid negated, so one `minimum.reduceat`
     yields all four bounds): **79 → 59 ms** on the 32k case. The gathers were
     21 ms of a 52 ms build and the node bounds go to the shader as f32 anyway.

   Both are kept. Neither is the step change, and the reason is structural: the
   build walks the whole primitive array **17 times**, once per level.

   **What removed it for the case that matters is not making it faster but not
   doing it.** `build_bvh_cached` keys the tree on the *content* of the primitive
   bounds — identity would never match, since the caller rebuilds those arrays
   from the scene every time, and a shape check would hand back the wrong tree
   for a moved molecule. Hashing 85k bounds costs a millisecond or two against a
   build of hundreds. Re-rendering the same geometry: **904 ms → 169 ms**,
   measured within one process so the machine's load affects both sides equally.
   Changing a colour or a light still hits the cache; moving the molecule does
   not. `bvh.build_count` exists only so a test can see this working, because a
   cached tree and a rebuilt one are otherwise indistinguishable.

   **Still open: the first render.** The step change there is a **Karras LBVH** —
   one Morton-code sort, after which every internal node's range and split are
   determined independently and vectorise into two or three passes, with node
   bounds from a sparse table (log n elementwise `minimum`s over the sorted
   boxes, no gather). It needs `node_meta` to carry an explicit right-child index
   instead of assuming siblings are adjacent, and a leaf-collapse pass. Estimated
   ~40 ms against 241, at some cost in tree quality. Not attempted.

   **A leaf-size sweep (4/8/16/32/64) was attempted three times and is not
   reportable.** Another agent's suite pushed the machine to load 33–44 and the
   build times came back non-monotonic in the leaf size — 690/817/513/215/322 ms
   for work that can only decrease. Interleaving the repeats and taking the min
   per configuration did not rescue it. Re-run it on a quiet machine before
   believing any leaf size but the current 4.

   **Welding got its own win.** `_triangle_edges` was 45 ms, half of it
   `np.unique(..., return_inverse=True)` sorting 330k edge ids to find 55k
   distinct ones. The ids are dense and bounded — three per grid node — so a
   mark-and-number pass over that range replaces it, and `flatnonzero` returns
   them already ascending, which is the order `unique` gave, so the vertex
   numbering is unchanged. **45 → 34 ms.**

   **Welding on the GPU was designed and not built.** It needs an
   `atomicCompareExchange` claim per grid edge, and the natural one-pass form
   spins waiting for the winning thread to publish its index — which has no
   forward-progress guarantee across workgroups. The spin-free shape is three
   passes (mark, number the marked, map), 25 MB of slot array at 128³, and it
   assigns vertex indices in arbitrary order, so determinism has to be restored
   by a host-side sort and a re-gather. Roughly 20 ms of prize against that; the
   analysis is here so the next attempt starts from it.

2. **The browser port — in progress. There is one engine, and Qt and the GPU
   binding are moving behind seams.**

   **The user's constraints, and they decide the architecture:** *no duplication
   of the engine*, *~90 % of the app lives in the WebGPU window*, and *shipping
   pixels will be too slow*. A JavaScript renderer was designed and **rejected
   against those**: it would have had to grow a JS ray tracer, a JS BVH build
   and a JS marching cubes to reach parity with the eighteen WGSL files, and
   every future pass would need writing twice.

   **What settles it is four measurements, taken from the tree:**

   | measured | value |
   |---|---|
   | wgpu-py methods the engine calls | **20**, plus ~25 enum constants |
   | WGSL files behind them | **18**, incl. `raytrace`, `bvh`, `mc_vertices`, `edt` |
   | distinct QPainter primitives in `internal_gui.py` | **6** (91 sites, 1700 lines) |
   | chimol modules importing Qt | **24 of 119**, 13 of them `app/*` panels |

   Thirty-four of the thirty-eight `wgpu.*` names are **WebGPU specification
   constants** — the same integers and strings in a browser — and three more
   appear only in docstrings. That leaves **one** backend-dependent name,
   `gpu.request_adapter_sync`, which is why the seam is ~200 lines rather than a
   second renderer. And `internal_gui`'s `_paint_*` methods already take the
   painter **as a parameter**, so swapping it is wiring.

   **Landed.**
   - *Phase A* — the engine no longer needs Qt to import. `renderer/base.py`
     (annotations only), `colors.py` (two `Qt.UserRole` ints), `io/structure.py`
     (`QFileDialog`), `internal_gui.py` (two modifier masks), `cmd/animation.py`
     (`QTimer`) and `cmd/exporting.py` (a `QThread` subclass, now built by a
     cached factory rather than a module-scope `class` statement). Both
     `chimol/__init__.py` and `renderer/__init__.py` eagerly imported `MolView`,
     so *every* module in those packages required a window system — both are now
     :pep:`562` lazy. **15/15 engine modules import with Qt blocked.**
   - *Phase B* — `renderer/gpu/` is the only place allowed to name the binding.
     `api.py` keeps wgpu-py's spelling so call sites read unchanged
     (`from .gpu import api as wgpu`); `enums.py` states the spec constants
     outright; `native.py` holds the one real call. `wgpu_backend.py`,
     `compute.py` and `wgpu_view.py` are retargeted. `test_gpu_seam.py` fails on
     a new importer of `wgpu` and on any drift between our constants and the
     binding's. **161 passed / 6 skipped** across the render, compute, BVH,
     volume, lighting and view suites — the seam is a rename layer.

   **Answered — and the first answer is the opposite of what was assumed here.**
   - `wgpu.backends.js_webgpu` in wgpu-py 0.32 is an **explicit stub**
     (`# NOTE: this is just a stub for now!!`; `get_preferred_canvas_format`
     raises `NotImplementedError`; no device, buffer or pipeline API). So
     `rendercanvas`'s pyodide backend has nothing to drive and **does not**
     collapse the two drivers. The browser backend is a second module beside
     `native.py`, written against `js.navigator.gpu` through `pyodide.ffi`.
   - **The sRGB worry was backwards.** `navigator.gpu.getPreferredCanvasFormat()`
     returns `bgra8unorm` or `rgba8unorm` — **never** an `-srgb` variant. The
     default is already correct, and the trap is sprung only by a well-meaning
     "fix" that adds `viewFormats` + `createView({format})`. The guard is
     therefore a *prohibition*, not a conversion.
   - **`cerbsim/webgpu`** (the reference the user supplied) is read, not adopted.
     Its `engine.js` calls `createPipelineLayout({bindGroupLayouts: [one]})`
     unconditionally, while `silhouette.wgsl` and `overlay.wgsl` each declare
     `@group(1)`; and its depth texture is `RENDER_ATTACHMENT` only, so it
     cannot be sampled — which is exactly what pass 2 does. Its Pyodide
     device-request and heap-view technique is the part worth taking.

   **Phase C, first half — landed.** The chrome no longer knows what a toolkit
   is. `renderer/ui/painter.py` defines **six** operations — `fill_rect`,
   `stroke_rect`, `gradient_rect`, `text`, `push_clip`/`pop_clip` — and
   `renderer/ui/qt_painter.py` implements them with the same `QPainter` as
   before. `internal_gui.py`'s `paint` and its seven `_paint_*` methods lost
   their `QtGui`/`QtCore` parameters entirely.

   Deliberately **not** a `QPainter` with the names changed. `QPainter` is a
   state machine — thirty-one `setPen`s and twenty `setBrush`es feeding
   eighteen `drawRect`s and fourteen `drawText`s — and ported literally that
   state would have to be tracked while emitting vertices, where a stale brush
   is a mis-coloured quad rather than an error. Every call now carries its own
   colour, so each maps to a fixed number of quads: one for a fill, one plus
   four edges for a stroke, one with per-vertex colour for the gradient, one
   per glyph for text, a scissor for a clip.

   Two small things fell out: `COLOR_BUTTON_STOPS` became RGB triples (parsing
   `"#ff0000"` was the last thing needing `QColor`), and its disabled grey is
   now `_grey_of`, which reproduces `QColor.value() // 3 + 60` exactly —
   `value()` is HSV value, i.e. the largest component, so every saturated stop
   greys to 145.

   **Proof: all four baseline PNGs and the inventory came back byte-identical.**
   That is the right bar for this step — a refactor that changes pixels is
   indistinguishable from a wiring mistake, and a swapped colour or a dropped
   hover fill is exactly what this shape of change gets wrong. Pinned by
   `test/test_chrome_painter.py`, which also blocks Qt in a subprocess and
   imports `internal_gui` to prove the toolkit is gone.

   **Phase C, second half — landed.** The chrome is quads, on the GPU, and it
   is the default. `renderer/ui/quad_painter.py` appends into one interleaved
   array; `renderer/wgsl/ui.wgsl` draws it in the existing second pass, beside
   the silhouette. One pipeline serves the whole panel because the atlas
   carries an **opaque block** — a rectangle is a textured quad that samples
   white — and clipping rides on the vertex rather than as a scissor, so the
   panel stays one draw call.

   **The measurement that justifies it is the scaling, not the speed-up.**

   | viewport | `QPainter` + image | quads | uploaded |
   |---|---|---|---|
   | 1280×860 | 2.94 ms | 1.31 ms | 4.4 MB → 107 KB |
   | 2560×1720 | 6.71 ms | 1.37 ms | 17.6 MB → 107 KB |
   | 3840×2160 | 10.06 ms | 1.42 ms | 33.2 MB → 107 KB |

   The old cost tracks **viewport area** — it rasterises every pixel of a
   mostly-empty image — and the new one tracks **content**, which does not
   change when the window does. At 4K that is 7× less CPU and **318× fewer
   bytes**. A whole frame of chrome is 313–608 quads.

   Deleted with it: `CHROME_INTERVAL`, `_chrome_cache`/`_chrome_key`/
   `_chrome_painted`, `invalidate_chrome` and its three call sites. All of it
   existed only because the paint was expensive; once a frame is ~1.4 ms,
   deciding whether to rebuild costs more than rebuilding, and **the panel is
   simply always current** instead of allowed to lag.

   `_chrome_image` survives for the three things that genuinely are images or
   are drawn once — a traced frame, the 3-D labels, the rubber-band selection
   box — and returns `None` for an ordinary frame, which now rasterises nothing
   on the CPU and uploads nothing.

   *Trap the seam caught, working as intended:* `FilterMode.linear` was not
   declared in `renderer/gpu/enums.py`, because nothing had needed it. The atlas
   is baked at 4× and sampled down, so it wants linear where the overlay image
   wanted nearest. Adding a constant is now a deliberate edit in one file that a
   guard test checks against the binding.

   **Phase D — landed. The desktop side of the port is done.**
   `chimol/host/events.py` holds the button and modifier values, so
   `mouse_modes` decides what a click means without importing Qt to compare
   against `Qt.LeftButton`. Named **`host`, not `platform`**: a package called
   `platform` beside modules whose directory is sometimes on `sys.path` would
   shadow the standard library's, which this repository has already paid for
   once with `chisurf/math/` and the stdlib `math`.

   `test/test_engine_is_portable.py` is the exit criterion, as four assertions:
   **21 engine modules import in a process where Qt cannot be imported**; no
   module outside `renderer/gpu/native.py` imports the binding; no module
   outside a 16-entry host list imports Qt at module scope; and — the one that
   makes it shrink — an entry that no longer needs to be in that list fails.

   **The host list is the remaining worklist, and it is mostly one job.**
   Thirteen of its sixteen entries are `app/` panels — `objects_panel`,
   `hierarchy_panel`, `controls_panel`, `sequence_dock`, `timeline_panel`,
   `menu_bar`, `settings_table`, `config_editor`, `volume_panel`, `rmf_panel`,
   `demos`, `picking`, `molview_main_window` — which draw *with Qt widgets what
   the in-viewport panel already draws with quads*. So most of that list closes
   by moving those panels into the chrome, not by editing them. That is also
   the "~90 % of the app lives in the WebGPU window" the user asked for, and it
   is now the same job as finishing the port rather than a separate one. The
   other three are the widget (`wgpu_view`), its scene builder (`view`) and what
   is left of the image overlay (`gui_overlay`).

   **The browser renders — 148L, on the browser's own WebGPU (2026-08-11).**
   `renderer/gpu/browser.py` is the second backend beside `native.py`;
   `chimol/web/` is a loader, a demo and a dev server. `boot.js` holds no
   pipeline, no buffer and no draw call — every frame is the same Python, and
   the same nineteen WGSL files, the desktop runs. The demo draws 1363 sphere
   impostors of T4 lysozyme *parsed in the browser* by chimol's own PDB reader,
   plus the panel as quads.

   **Drive it with Playwright, not the Chrome tools.** The browser tools reach a
   Chrome that is **not on the same host** as the shell: a server answering
   `200` to curl gives that Chrome `ERR_CONNECTION_REFUSED`, on `localhost` and
   `127.0.0.1` alike, with the sandbox disabled — and every read lands on
   `chrome-error://chromewebdata/`, which is also why `navigator.gpu` read as
   false. Playwright's Chromium runs in the same sandbox and works with
   `--enable-unsafe-webgpu`. `test/test_browser_render.py` does the whole thing
   and is marked `slow`.

   **Four things the browser found that Python could not, and only one is a
   translation bug:**
   - `device.adapter` is a wgpu-py convenience with no WebGPU equivalent, read
     unguarded in the renderer's constructor — so the failure landed several
     layers from anything to do with adapters;
   - `createBufferWithData` does not exist either; the specification's way is
     `mappedAtCreation` + `getMappedRange` + `unmap`;
   - positional arguments needed converting as much as keyword ones, which
     `queue.writeTexture(destination, data, layout, size)` reports only as
     `Overload resolution failed`;
   - **the engine still depended on the host application.** `io/atoms.py` took
     its atom dtype from `chisurf.core.fio.structure.coordinates`, and
     `io/__init__.py` imported every reader eagerly — so asking for the
     self-contained PDB parser pulled in the density-map reader, marching cubes
     and scipy. Qt was never the only thing tying the engine to a desktop, and
     the portability guard did not catch this because it only blocks Qt.

   *Trap for the dtype fix:* `test_atom_rows.py` asserts `ATOM_DTYPE is
   atom_dtype` — **identity**, deliberately, so the core owns it. The fallback
   therefore keeps the core's object when the core is importable and defines an
   equal copy only when it is not.

   **Where to pick this up next — three, asked for directly, in this order.**

   1. **Selections must work without Qt.** `renderer/view.py::_update_selection_highlight`
      (`:8898`) builds the marker geometry and lives in the **Qt widget**, so the
      browser has no path to it and a strip selection highlights nothing in 3-D.
      Move it into the engine beside the other scene builders. It pays twice --
      the browser gains it, and the desktop and browser stop being able to
      disagree about what a selection looks like.
      *Do not port it as it stands:* the markers set `meta["px_mode"]`, which the
      WGSL backend **never reads** (it reads only `size` and `world_radius`), so
      pixel-mode markers get world-radius behaviour -- size varying with depth,
      which is the scattered dots in the user's screenshot. Fix that first or
      the port carries the bug across. See [known-issues](/references/known-issues.md).

   2. **Delete the Qt sequence dock.** `app/sequence_dock.py` duplicates what the
      in-viewport strip already draws with quads. Removing it strikes a line from
      `HOSTS` in `test/test_engine_is_portable.py` -- 16 → 15 -- and it is the
      cheapest of the thirteen `app/` panels to close, because the replacement is
      already shipping and already tested. Check `app/molview_main_window.py` for
      its registration and the `Seq` toolbar button.

   3. **Neighbour counting on the GPU.** The demo's occlusion uses a brute-force
      `(n, n)` numpy pass, and `compute.build_grid` is numpy too -- so the *only*
      GPU part today is the occlusion integral in `occlusion.wgsl`.

      **Measure before assuming it is a win.** Forced with `CHIMOL_COMPUTE=gpu` on
      148L's 1363 atoms, the existing GPU integral is **806 ms against numpy's
      39 ms** -- twenty times slower, because `MIN_WORK_ITEMS` is 20 000 and 1363
      work items cannot amortise the dispatch and the buffer round-trip. A GPU
      neighbour count at that size will lose by more, not less: it is cheaper work
      than the integral it feeds. The shape that wins is one dispatch that does
      grid, count and integral together without a round-trip between them, and it
      wins on a structure with tens of thousands of atoms, not on the demo.
      A counting sort on the GPU is histogram → prefix sum → scatter; `bvh.wgsl`
      already has a prefix sum to copy from.

   **Also still open.**
   1. **Move an `app/` panel into `InternalGui`.** Start with `objects_panel` /
      `hierarchy_panel`: `InternalGui` already draws that list, so this is
      mostly deleting a duplicate. Each panel that moves strikes a line from
      `HOSTS` and gains the browser a feature.
   2. **Labels are still an image.** They are text, so they are quads —
      `_collect_labels` and `project_to_screen` already give position and
      string. Doing them leaves only the traced frame and the selection box on
      the texture path, and deletes `paint_labels`.
   3. **The browser backend**, beside `renderer/gpu/native.py`: `js.navigator.gpu`
      through `pyodide.ffi`. The device request is **async**, so the bootstrap
      must resolve it before the engine starts — if `await` leaks into the
      engine, the desktop path grows an event loop it does not need. Measure
      Pyodide's per-frame cost early; it is the one risk that can still change
      the shape of the answer.
   4. **A loader page.** No packaging change is needed for the assets:
      `[tool.setuptools.package-data]` already ships `*.png`, `*.json` and
      `*.wgsl`; `*.js` and `*.html` would need adding, and **not** `*.ts`,
      which is Qt Linguist.

   **Superseded — the atlas plan, for reference.**
   1. **Bake the glyph atlas.** The chrome's font is `QFont("Menlo")` at
      `InternalGui.FONT_PT`. The character set is ASCII plus exactly seven
      non-ASCII glyphs: `▾ ▸ ▴ ─` in the panel and menus, and `◀ ■ ▶ ▼` in the
      transport (`MOVIE_BUTTONS`, which also uses `|`, `S` and `F`). A **bold**
      face is needed too — one caller, a menu's title row. Bake with Qt or PIL
      at build time, commit the `.png` and a metrics `.json`; *using* it must
      need neither. **No packaging change is required**: `pyproject.toml`'s
      `[tool.setuptools.package-data]` already ships `*.png` and `*.json` for
      every package — checked, so do not add a glob for them. (Do not reach for
      `*.ts` for anything: that glob is Qt Linguist translation sources.)
   2. **`QuadPainter` + `renderer/wgsl/ui.wgsl`.** One alpha-blended pipeline,
      no depth. Blend **premultiplied**, matching what `overlay.wgsl` composites
      today, or light backgrounds get dark fringes — visible only on white.
      Clipping is one call site but governs the menu, so it needs a scissor or
      a per-quad clip rect.
   3. **Wire it and delete the old path.** `gui_overlay.paint_chrome`,
      `paint_chrome_into`, `image_from_rgb`, and in `wgpu_view` the
      `_chrome_cache` / `_chrome_key` / `_chrome_painted` / `CHROME_INTERVAL` /
      `invalidate_chrome` group — the cache exists *only* because the paint was
      expensive. `paint_ray_image` keeps its texture; that one is genuinely an
      image.
   4. **Benchmark** at a quarter-million beads, labels on and off, and update
      `docs/development/benchmarks.md`.

   Parity is judged on the **control inventory**, not pixels, from step 1
   onwards: the atlas moves text metrics on purpose. `test_chrome_painter.py`'s
   byte-identity assertions are for the refactor only and must be relaxed to
   the inventory comparison when the atlas lands — do that deliberately, in the
   same change, rather than discovering it as a failure.

   **Then Phase D** — `platform/{events,desktop}.py`, then
   `test_engine_is_portable.py`. Only then the browser backend and a loader
   page.

   **The chrome is a per-frame CPU rasterise, and that is a desktop defect, not
   only a portability one.** `wgpu_view.py:519` documents its own cost:
   *"painting this was 9.6 ms of a 21 ms frame with a quarter of a million beads
   on screen"* — ~46 % of the frame, spent rasterising a full-viewport RGBA
   image with `QPainter` and uploading it as a texture. The mitigation is a
   **timer**, `CHROME_INTERVAL`: the panel is deliberately allowed to be stale
   because repainting it when it changes is too expensive. And the same
   docstring names the case where even that fails — *"Labels are the exception
   — they move with the camera — so a scene that has any is painted every frame
   as before."* Drawing the chrome as quads deletes the cost, the staleness
   compromise and the last Qt import from the engine together.

   **The before-half is captured.** `test/chrome_baseline.py` writes four states
   — `panel`, `panel_and_sequence`, `menu_open`, `movie_transport` — to
   `test/renders/chrome_baseline/` as PNGs plus an `inventory.json` recording
   both what the layout holds and every control a 4-px sweep of `hit_test` can
   actually **reach** (11 / 56 / 66 / 81). Parity is judged on that inventory,
   not on pixels: the glyph atlas deliberately moves text metrics. *Trap, and it
   cost a capture:* the strip is gated on `sequence_visible` and the transport
   on `state[1] > 1`, so a capture that only sets the rows produces four
   identical images and an inventory that cannot tell the states apart.

3. **Metaball "not flubber enough" (user request, still untouched).** There is
   **no metaball scene in the frozen baselines**, and now there never can be —
   so this is judged against the current render alone, or against a new
   WGSL-only reference pair you capture yourself. Knobs in
   `chimol_display.json`: `sigma_factor 4.0` (fusion — merges beads into smooth
   lobes, the main lever), `alpha 0.55`, `shininess 96`,
   `specular_strength 0.85`, `rim_strength 0.55`, `iso_value 0.1`.
   **Tried and rejected:** `sigma_factor` 9.0 ("a featureless egg") and 6.5 (the
   surface encloses ~93,700 Å³ around a protein whose own envelope is ~25,000,
   and no `iso_value` pulls it back — even 0.95 bottoms out at 71,400). 3.0 and
   3.5 wrap a helical bundle too tightly. The useful range is narrow; see
   [pymol-parity](/plugins/pymol-parity.md).

4. **Atomic spheres are still tessellated.** `balls.impostor_min_atoms` applies
   to *beads* only, so `show spheres` on an atomic structure emits **374,112
   triangles** on 148L where the impostor path would emit ~2,770 — measured, and
   the impostor path itself is verified at **120 triangles against 19,200 with
   silhouette IoU > 0.97** (`test_wgsl_parity.py::TestImpostorsOnTheGpu`). The
   change is in the **scene builder** (`renderer/view.py::_update_atoms`), not
   in the backend. It is now *cheaper* than it was: with OpenGL gone there is no
   second renderer to keep in step, and the baselines it would have invalidated
   are frozen anyway — so the comparison to make is before/after in WGSL.

5. **Wide lines.** `meta["width"]` is ignored: WebGPU's `line-list` is 1 px
   only, so a width needs expanding to quads in `line.wgsl`. `lines` and
   `ribbon` are the representations that carry it.

6. **An open question for the user, not a defect.** The off-axis key light plus
   fill that `wgpu_backend`'s old hardcoded `DEFAULT_LIGHTING` accidentally
   described is plausibly the *"the WGSL render looks better"* recorded earlier
   — it models a ribbon where the configured head-on rig lights it flatly. It is
   now a **setting**, not a backend's private constant, so if that look is
   wanted it belongs in `chimol_display.json`'s `lighting` section. Asked twice;
   not yet answered.

## What is deliberately not on that list

- **`test_screenshot_helper.py` still exercises a `QOpenGLWidget`.** That is
  `screenshot.py`'s generic GL-compositing path, not chimol's renderer — it is
  dead for chimol but still correct for any GL widget. Left alone on purpose.
- **The `dots` glyph is twice the size of the frozen baseline's.** The baseline
  is *wrong*: OpenGL drew a 4 px dot for a requested `gl_PointSize` of 8, with
  dpr 1.0 and a point-size range of [1, 64] ruling out scaling and clamping.
  The WGSL renderer draws the documented size. Recorded in
  [known-issues](/references/known-issues.md); do not "fix" it toward the
  baseline.

## The bug that was not in the renderer (2026-08-10)

"The WGSL cartoon is markedly darker than the baseline against a **white**
background, and matches against black" is a good bug report — it is specific,
reproducible and it points somewhere. It pointed at the only place a clear colour
legitimately reaches shading, the fog term, and the answer was not there.

`capture_gl_baseline.py`'s `RESET` preamble did not restore `occlusion.enabled`,
and `occlusion_enabled_off` runs **immediately before** `bg_white`. Five
baselines were therefore photographed with ambient occlusion switched off, while
the WebGPU replay — a fresh process, config default — had it on and was right.
The scene's packed colours carry occlusion pre-multiplied, so `grey80` arrives at
a mean of **0.455** with AO on and **0.856** with it off. That ratio is the whole
of the difference; nothing about the background was ever involved.

What settled it in one look was a three-panel PNG — GL | WGSL AO-on | WGSL AO-off
— where the third panel lands on the first. Two scalars had already pointed the
wrong way before that (lit-pixel IoU read **1.000** for a scene that was plainly
wrong, because a white background counts as lit; whole-frame means differed by
4 %). `labels` was an unplanned control: it re-captured **byte-identical**,
because sticks have no AO path at all.

Fixed by adding `occlusion.enabled` and `fog` to `RESET`, and — because the
comment "keep the two lists in step" was already there and did not keep them in
step — by `missing_resets()`, which diffs the settings the scenes assign against
the ones the preamble restores. `main()` refuses to open a window when it is
non-empty, and `test/test_wgsl_parity.py` fails on it with no GPU.

**Two constants found on the way, both real and neither the cause.** They were
transcribed between backends instead of shared, which is the same defect as the
`RESET` list in a different costume:

- `renderer/depth_cue.py` now holds PyMOL's `SceneSetFog` planes; `qtgl` and
  `wgpu_backend` both call it. The WGSL renderer had had **no depth cue at all**.
- `renderer/lighting.py` now holds the light rig. `wgpu_backend` had carried a
  hand-written `DEFAULT_LIGHTING` dict documented as "matching the OpenGL
  backend's defaults" which matched none of them: key light 25° off-axis where
  the configured one points **straight down the camera**, `fill=0.45` where the
  config asks for **no fill light**, `ambient=0.28` against `0.45`. Its shader
  also added the environment reflection at a flat 10 % where GL blends it through
  a Fresnel `mix` weighted by specular strength.

**Open question for the user, and it is a judgement call not a defect:** the
off-axis-key-plus-fill rig that `DEFAULT_LIGHTING` accidentally described is
plausibly the "the WGSL render looks better" the user recorded, because it models
a ribbon where the configured head-on rig lights it flatly. That is now a
*setting*, not a backend's private constant — so if the modelled look is wanted,
it belongs in `chimol_display.json`'s `lighting` section, where **both**
renderers get it.

## Things that are settled — do not re-litigate

- **The camera is correct.** IoU 0.981 with the matrices as written, once cropped
  by `scene_rect`. Transposing the rotation gives 0.274, flip-x 0.367, flip-y
  0.341. An earlier "the model is mirrored" conclusion was a mis-guessed crop.
- **Colours are correct**, including `spectrum count`'s rainbow.
- **Ambient occlusion is respected**, and the on/off switch matches GL in both
  backends. It arrives twice — pre-multiplied into vertex colours *and* as a
  separate attribute damping ambient/rim/environment — which is what the GL
  shader does too.
- **Backgrounds and transparency work** as of `6464a2274`.

## Traps that cost real time here

- **A parallel implementation that is not the default is not tested.** The WGSL
  renderer had its own green suite and 31 holes in it, every one invisible until
  the default flipped. If you are building a replacement for anything here, the
  cheapest test you have is making it the default and reading the failures.
- **A grab taken before the first present is a black viewport, not a broken
  renderer.** `request_draw` only schedules, and pumping Qt's event loop does
  not help. `test/screenshot.py::force_render_canvases` forces every canvas;
  `shoot()` calls it.
- **A translucent Qt child cannot overlay a presented GPU surface.** Uncleared
  backing store composited over the frame turns a rainbow cartoon
  salmon-and-blue — which reads exactly like a channel-order bug; clearing it
  makes the molecule vanish, because the child *covers* the surface. Composite
  inside the render pass.
- **Two different pixel sizes live in the widget.** The contract (framing,
  picking, the panel's layout) is in **logical** pixels; only the GPU target is
  in device pixels. Reporting the surface size from `scene_width()` left the
  aspect stale until the first `resizeEvent`.

- **Always attach `cmd.set_error_callback`.** A harness that drops it turns a
  refused command into a rendering difference two layers away. ~100 commands ran
  silently refusing before this was noticed.
- **Crop by `scene_rect`**, never guess. The object panel is a right-hand column
  and the sequence viewer a top band, both drawn *inside* the GL widget.
- **A lit-pixel IoU counts a white background as lit**, so it reads ~0.12 on a
  correct render. The image is the artifact; the number is a hint.
- **Discard the first framebuffer grab** after a rebuild — it can come back as
  uninitialised noise and poison any brightness comparison.
- **Bind the `QApplication`.** An unreferenced `QApplication([])` is collected and
  the next `QWidget` aborts the interpreter with no Python traceback.
- **A grab taken before the first present is a black viewport, not a broken
  renderer.** `request_draw` only *schedules*. Pumping the Qt event loop does
  not help, because the canvas decides when to draw. Call `force_draw()` on
  every canvas before the shutter — `test/screenshot.py::force_render_canvases`
  does it, and `shoot()` calls it.
- **A translucent Qt child cannot overlay a presented surface.** Two
  arrangements were tried for the object panel and both failed in ways that
  read as renderer bugs: without clearing the child's backing store, uncleared
  memory composited over the frame and turned a rainbow cartoon
  salmon-and-blue (which looks exactly like a channel-order bug); with the
  clear, the molecule vanished, because the child covers the surface rather
  than blending with it. The chrome is painted to a premultiplied RGBA image
  and composited as a textured quad inside the render pass — which is also the
  only form a browser could use, and what `kind == "text"` labels will need.
- **Suspect the baseline, not only the renderer.** A leaked setting does not
  announce itself; it looks like whichever renderer you trust less, and the
  baseline is the half nobody re-derives. Before spending a day inside a shader,
  render the *same* scene both ways with the suspected setting forced each way —
  three panels, one image, one minute.
- **A test module that imports the capture harness moves the settings
  directory.** `capture_gl_baseline` used to call `os.environ.setdefault(
  "CHISURF_SETTINGS_DIR", mkdtemp())` at *import*, so importing it for `SCENES`
  or `missing_resets` changed which display config every later test in the
  process read — and the damage surfaced three tests away as an unrelated
  assertion about occlusion keys. It is in `isolate_settings()`, called from
  `main()`, now. See [global-setting-test-isolation] for the general shape: one
  process-wide dict means one test can break a *different file*.
- **A setting deleted from the packaged defaults is still in every existing
  user's config.** `DISPLAY_CONFIG_MIGRATIONS` changes a value and
  `DISPLAY_CONFIG_KEY_MOVES` moves one; neither can delete, so a removal reached
  nobody who already had the file. `sticks.ambient_occlusion` had been "removed"
  and was still live on every real profile, while the guard test asserting it was
  gone passed — because it runs on a fresh directory.
  `DISPLAY_CONFIG_KEY_REMOVALS` (version 11) is the third migration kind.
- **Compare order-independent summaries** (area, centroid, bbox) for meshes, not
  sorted rounded centroids — f32-vs-f64 flips ties and reports a correct kernel
  as wrong.

## Commits, in order

**Session 1 (Phase 0–2 groundwork).** `0b90174d9` Phase 0 gates ·
`58996c37c` GL baselines · `58db3aea4` AO switch fix · `756e2df06`
settings-kind test · `fa7377580` SceneSink · `79b3d6811` pack.py ·
`128cc86ab` WGSL renderer · `78780b602` scene_rect · `2842d8e30` is_empty fix ·
`ee39098a6` compare harness · `6464a2274` transparency + background

**Session 2 (the port lands).**
`1b5a4821d` the contaminated baseline, `depth_cue.py` + `lighting.py` ·
`4aa10d023` impostors, lines, points; `shading.wgsl` prelude ·
`da5a1f7d9` the viewport runs on WGSL (`wgpu_view.py`, `camera_state.py`,
`gui_overlay.py`) · `8fda1ded5` WGSL becomes the default, and the 31 gaps that
exposed · `76df2fcfd` **the OpenGL renderer is deleted**.

# Detail and history

# Where to pick this up (2026-08-10, superseded twice — history only)

*Kept for the measurements and the ruled-out approaches in it. Every "next
step" it names is either done or restated in the handover at the top; read that
one.*

**Phase 0 is complete — all three gates passed (2026-08-10). Nothing in
`chisurf/plugins/chimol/` has been modified yet.** Prototypes live in the session
scratchpad; the numbers below are the record.

Next, in order:

1. ✅ **Done — GL baselines captured (2026-08-10).** 23 scenes, 46 PNGs, in
   `chisurf/plugins/chimol/test/renders/gl_baseline/`, by
   [`test/capture_gl_baseline.py`](chisurf/plugins/chimol/test/capture_gl_baseline.py).
   Each scene records the **18-float camera** in `manifest.json`, so the WebGPU
   half replays `set_view` and produces a directly comparable frame; each also
   records its full command sequence including a `RESET` preamble, so scenes are
   independent of run order. **One gap remains**: the point-sprite impostor path
   is not covered, because `balls.impostor_min_atoms` applies to *beads*, not to
   atomic `show spheres` — that baseline needs a bead/integrative model and is
   still to do.
2. ✅ **Done — Phase 1, `SceneSink` (2026-08-10, `fa7377580`).**
   `renderer/headless.py` builds the scene and rasterises nothing;
   `MolView(renderer_factory=SceneSink)` selects it. Two assumptions went with
   it: the Qt chrome was guarded on the renderer *existing* rather than on it
   being a `QWidget`, so a windowless backend fell into the branch that sets
   `self._renderer = None`; and `Renderer.widget()` returning a `QWidget` is the
   assumption a second backend cannot meet — it returns `None` now and the
   viewer handles that. Verified under `QT_QPA_PLATFORM=offscreen`, where GL has
   no context at all: cartoon 19,908 verts / 39,032 tris, sticks 33,216, spheres
   374,112, surface 55,832 — **and the CPU ray tracer renders that same scene**,
   so two windowless backends already share one scene and one camera. The sticks
   figure independently reproduces the 33,216 triangles recorded for 148L, which
   is the measure of what instanced impostors replace (my WGSL prototype: 2,770
   for the sphere rep, ~135× fewer).
   `test/test_headless_scene.py` compares the two backends **array by array**
   across four representations — no GPU needed, and it fails on the specific
   array that changed. Trap it caught: `SceneSink` first copied the Qt backend's
   habit of widening the far plane to protect depth precision, which broke
   `set_view_state(get_view_state())` at slot 16 (166.78 → 1167.82). There is no
   depth buffer here, and a camera that does not survive a round trip cannot
   reproduce a frame.
   **Not yet done in this phase:** `app/cli.py:_make_cmd` still uses
   `MockWindow`; switching it to a real `MolView(renderer_factory=SceneSink)` is
   what finally lets `chimol cli` render, and should shrink or delete
   `testing/mock_viewer.py`.

3. **Superseded — the original Phase 1 note.** `_update_view` opens with
   `if self._renderer is None: return`, and the Qt chrome after renderer
   construction (`renderer/view.py:2479`) is one contiguous block guarded by
   `if renderer is not None:`. That single early return is the only reason the
   existing headless CLI can run commands but not build a `Scene`. A null renderer
   plus a `renderer_factory` argument fixes it — not a refactor. Gate it with a
   test asserting the Qt path and `SceneSink` produce bit-identical arrays.
3. 🔄 **Phase 2 — in progress.** Landed: `renderer/pack.py` (`79b3d6811`) and
   `renderer/wgsl/mesh.wgsl` + `renderer/wgpu_backend.py` (`128cc86ab`). The
   WGSL renderer draws 148L cartoon on Metal and **the fold, orientation and
   cartoon geometry match the baseline**, so replaying `set_view` across backends
   works.

   **Next, and it must come before any parity claim: build the comparison
   harness.** The GL `view` grab is 1278 px wide and contains the sequence strip
   across the top and the object panel down the right, so the molecule column is
   *not* the whole image — an IoU or a pixel diff taken against it measures the
   crop, not the shading. I measured 0.362 and 0.277 for two rotation
   conventions and neither number means anything until the scene column's
   offset and size are read from the renderer rather than guessed. The manifest
   already records the camera; it should also record the scene-column rectangle.

   **USER JUDGEMENT (2026-08-10): the WGSL render looks *better* than the GL
   one.** So the material is not to be tuned back toward the OpenGL image. Parity
   here means feature inventory — every representation, setting and cue still
   present and controllable — and explicitly **not** matching GL pixel for pixel.
   Record any deliberate look change rather than "fixing" it.

   **The camera is correct. There was never a camera bug — the harness was the
   whole problem.** With `scene_rect` recorded (cartoon: x=0, y=51, 1058×580
   inside a 1278×631 framebuffer) the silhouette overlap against the GL baseline
   is **IoU 0.981** with the matrices exactly as written. For contrast:
   transposing the rotation gives 0.274, flipping x 0.367, flipping y 0.341. The
   earlier 0.362 and the "the model is mirrored" reading were both artefacts of
   cropping 1078×571 at y=60 out of an image whose scene column is 1058×580 at
   y=51. **Do not re-open the camera; it is measured.**

   **What is genuinely still wrong is per-vertex colour correspondence.**
   Projecting individual vertices and sampling the GL baseline at the same screen
   position:

   | vertex | colour in the packed array | GL pixel there |
   |---|---|---|
   | 0 | 0.648 0.307 0.170 (orange) | 0.017 0.024 0.415 (blue) |
   | 10000 | 0.304 0.267 0.331 (grey) | 0.140 0.272 0.012 (green) |
   | 19907 | 0.254 0.549 0.946 (blue) | 0.639 0.111 0.035 (red) |

   **RESOLVED — it was never a renderer bug.** The user identified it from the
   picture in one line: the two images use *different colour spectra*, nothing is
   reversed. Chasing that down: in the headless replay, `color grey80`,
   `spectrum b` and `spectrum count` all produce **byte-identical** colour arrays,
   and `test/renders/wgsl/plain_vs_spectrum.png` shows the GL column responding to
   all three while the WGSL column is the same image three times. The renderer was
   faithfully drawing an uncoloured scene.

   The cause, once the error callback was finally hooked: `color` and `spectrum`
   were returning **"nothing is loaded -- use 'load <file>' or 'fetch <id>'
   first"**. A `MolView` built directly with `apply_payload` and a minimal window
   stub gets geometry — `show cartoon` works against that same viewer — but the
   command layer's *is-anything-loaded* check reads state the stub does not set,
   so the colour commands refuse. That inconsistency is worth fixing on its own:
   two commands disagreeing about whether a viewer has a structure is the kind of
   split that will bite the CLI and the browser path too.

   **The process lesson, which cost most of the time:** the replay ran ~100
   commands without `set_error_callback`, so every refusal was silent and the
   symptom surfaced as a rendering difference. `capture_gl_baseline.py` hooks both
   callbacks and collects them into the manifest; any harness driving `Cmd` must
   do the same. See [[always-produce-pngs]] — the numbers said "mirrored camera"
   and "reversed ordering", and both were wrong; the four-panel image said
   "different palette" immediately.

   Superseded analysis below, kept because the ruling-out is what made the real
   cause findable.

   **Not an ordering bug — tested and ruled out.** See
   `test/renders/wgsl/colour_diagnosis.png`: four panels, GL baseline | WGSL
   as-is | WGSL with the colour array reversed | WGSL unlit. Reversing merely
   swaps which side is orange and which is blue; it does not restore the rainbow.

   **What the picture actually shows is that WGSL has only two hues where GL has
   five.** GL runs blue→green→yellow→orange→red across the fold. WGSL renders
   orange at one end and blue at the other with grey between — that is, it is
   interpolating between the *first and last* colours and nothing in between.
   And the packed array agrees with the WGSL image, not with GL: sampled at 0 %,
   50 % and 100 % along, it reads orange, grey, blue.

   So the question is not how the WGSL renderer draws the array. It is **why the
   OpenGL baseline shows a rainbow the array does not contain.** Either the Qt
   renderer colours from something other than `Geometry.colors` — a per-segment
   or per-object colour it applies itself — or `spectrum count` writes its ramp
   somewhere the packed scene is not reading. Test it by dumping the colour
   buffer the Qt renderer actually uploads, at the point of upload, rather than
   reading `Geometry.colors` and assuming that is what it gets. Note this does
   *not* contradict the Phase 1 array-equality result: that compared two viewers
   assembling the same `Scene`, which says nothing about what the Qt *renderer*
   does with it afterwards.

   Also unexplained: the packed colours are dark and desaturated (mid-chain rgb
   ≈ 0.30, 0.27, 0.33) because occlusion is pre-multiplied in, yet the GL
   baseline renders a vivid rainbow from that same array. Whichever backend
   treats the pre-multiplied occlusion differently is also the likely source of
   the grey wash in the WGSL image.

   Then the rest of the feature list, each proven by a screenshot pair:
   impostor spheres and capped cylinders (prototyped in Phase 0), transparency,
   `two_sided_lighting`, depth cue, silhouettes, labels.

Open questions deliberately not yet answered: whether `rendercanvas`'s **`pyodide`
backend** (it exists — see below) collapses the two drivers into one; and how the
sRGB mismatch is best handled (see the trap list).

# Why WebGPU rather than a second WebGL renderer

The obvious shape — keep the OpenGL desktop renderer and write a second WebGL one
in JS — was rejected after measurement. It means two renderers, two GLSL dialects
and two implementations of every compute kernel, permanently. The decisive fact:

**macOS caps OpenGL at 4.1, and compute shaders need 4.3.** Asked the real driver
on an M1 Pro:

```
GL_VERSION  = 4.1 Metal - 90.5      GLSL 4.10
GL_COMPUTE_SHADER -> UNAVAILABLE (GLError)
```

Apple deprecated OpenGL and emulates it over Metal. And **WebGL2 has no compute
shaders either** — WebGL 2.0 Compute was removed from Chromium and its spec marked
obsolete, with WebGPU named as the replacement.

| API | compute | macOS | Linux/Win | browser |
|---|---|---|---|---|
| OpenGL | GL 4.3+ | **no (4.1)** | yes | — |
| WebGL2 | **no** | — | — | no |
| Vulkan | yes | MoltenVK only | yes | no |
| **WebGPU / WGSL** | **yes** | yes (→Metal) | yes (→Vulkan) | **yes** |

WebGPU is the only row that spans all three targets, so it collapses the renderer
*and* the kernels to one WGSL source with a thin driver on each side.

# Phase 0 gate results (2026-08-10)

**Gate 3 — `wgpu-py` in a PyQt5 dock: PASS.** `wgpu` 0.32.0 + `rendercanvas`
2.7.2, `backend_type='Metal'` on the M1. `QRenderWidget` embeds as a *subwidget*
inside a real dock layout (central 3-D view + fixed-width object panel + bottom
console dock) and lays out at **870 × 485**. Two bonuses over OpenGL, both of which
solve long-standing pain:

- **`rendercanvas.offscreen` produces real pixels.** GL under
  `QT_QPA_PLATFORM=offscreen` returns black, which is why every render test needs a
  logged-in window server today. WebGPU offscreen rendered a correct image with
  15,712 distinct colours. This could put render tests in ordinary CI.
- **`win.grab()` captured *both* the 3-D surface and the Qt chrome.** The GL path
  cannot: the screenshot helper pastes the framebuffer over the widget area and
  hides overlay children, which once produced a whole-window grab showing no panel
  at all while it was plainly visible.
- `rendercanvas` also ships a **`pyodide`** backend — the browser driver may not
  need to be JS at all. Worth evaluating before writing one.

**Gate 1 — instanced impostors: PASS.** Sphere and capped-cylinder impostors in
WGSL, rendering real 148L heavy atoms (1,385) with CPK colours, plus a 162-bond CA
trace. **2 triangles per atom** instead of a tessellated mesh — for comparison, the
current GL path spends 33,216 triangles on a few hundred capped cylinders. The
lighting is transcribed from `qtgl.py`'s fragment shader (convex ambient/diffuse
mix, rim, fake-matcap environment reflection, PyMOL's linear two-plane fog) so the
two renderers cannot disagree.

One deliberate upgrade, not a regression: **these impostors write per-fragment
depth**, so a sphere intersects neighbouring geometry the way a tessellated sphere
does. The current GL point-sprite path computes a sphere normal but never writes
`gl_FragDepth`, so its spheres are flat billboards. The curved intersection seams
between overlapping atoms in the render are the proof.

The capped-cylinder fragment shader is **the same analytic capsule intersection the
CPU raytracer already computes** — so for the first time GL geometry and ray
geometry describe the same solid and can be tested against each other.

**Gate 2 — marching cubes on the GPU: PASS, with an honest ceiling.** MC is the
hard case: each cell emits a *variable* number of triangles, so the output needs
compaction (this prototype uses an atomic append counter; a prefix-sum would be an
optimisation of it). Against chimol's own numba `marching_cubes`:

| field | grid | numba | GPU | speedup | triangles | surface-area Δ |
|---|---|---|---|---|---|---|
| sphere | 48³ | 3.7 ms | 1.01 ms | 3.7× | 7868 = 7868 | 5.5e-09 |
| sphere | 64³ | 12.5 ms | 2.72 ms | 4.6× | 14300 = 14300 | 5.9e-09 |
| sphere | 96³ | 44.0 ms | 2.49 ms | **17.7×** | 32588 = 32588 | 1.7e-09 |
| blobs | 48³ | 7.0 ms | 1.26 ms | 5.5× | 9008 = 9008 | 3.5e-09 |
| blobs | 64³ | 10.1 ms | 1.30 ms | 7.8× | 16184 = 16184 | 3.2e-10 |
| blobs | 96³ | 34.4 ms | 1.85 ms | **18.6×** | 36708 = 36708 | 1.7e-09 |

Triangle counts are **exact** in every case and the speedup grows with grid size,
which is the direction that matters. But 4–19× is not the 229× the distance grid
gave — MC is atomic- and bandwidth-bound rather than compute-bound. **That is the
point of the gate: the GPU route generalises, but not uniformly, so each kernel
must be routed by measurement rather than by category.**

# Scene kernels on the GPU

Everything data-parallel in chimol's scene building and all of its ray tracing
now runs as WGSL compute on the same WebGPU stack the renderer draws with —
`renderer/compute.py` plus `wgsl/{grid,shade_atoms,occlusion,shadow_rays,
distance_grid,edt,mc_active,bvh,bvh_probe,raytrace}.wgsl`. The shaders are plain
WGSL a browser compiles unchanged, composed by concatenation because WGSL has no
`#include` — the same rule the render shaders follow.

| kernel | before | NumPy/scipy | WGSL compute | |
|---|---|---|---|---|
| **ray tracer**, 640×480 ssaa2, shadows, 1.3k spheres + 328 tris | 12.5–15.6 s (numba) | — | **60–75 ms** | **170–260×** |
| `occlusion_from_spheres`, 40k verts × 11k atoms | — | 1,139 ms | **16 ms** | 70× |
| sphere distance grid, 96³ × 11k atoms | 3,236 ms (numba) | 484 ms | **11 ms** | 43× / 294× |
| `directional_occlusion`, 40k verts × 11k atoms | — | 830 ms | **29 ms** | 29× |
| euclidean distance transform, 128³ | — | 328 ms | **32 ms** | 10× |
| `shade_from_atoms`, 40k verts × 11k atoms | 10 ms (numba) | 151 ms | **14 ms** | 11× |

**The whole SES surface build on 148L at 128³, three ways, identical mesh
(42,562 vertices / 85,092 faces) each time:**

| route | time |
|---|---|
| NumPy/scipy only | 983–1,397 ms |
| GPU kernels, grid round-tripping | 129–321 ms |
| GPU kernels, **grid resident** | **50–51 ms** |

Those absolutes were taken at load averages 12–20 — another agent was running a
suite — so read them as an upper bound; the ratios held steady across runs.
Keeping the grid on the device is worth **~2.5×** on top of having the kernels
there at all, and the pair together is roughly **20×** the pure-NumPy route. Do
not compare a single build against a single build; see the shader-compilation
trap below.

Agreement with the NumPy route is ~5×10⁻⁶ absolute (f32 against f64) and the
rendered frame is **identical**: a six-representation sheet built each way
differs in zero pixels above a threshold of 6. The traced image differs from the
numba tracer's in 0.012 % of pixels, all on silhouette edges.

**And on the actual nuclear pore it was 1030 ms a frame, of which the molecule
was two.** Reported as "can hardly rotate". Loading `PDBDEV_00000012` — 31 MB,
234,184 beads — rather than a synthetic stand-in is what found it, because the
cost was in the *sequence strip*, which a synthetic scene does not have:

| | |
|---|---|
| `_ca_rgba`, projecting per-atom colours onto residues in a Python loop | **683 ms** |
| building 234k Python tuples for the strip's colours | **395 ms** |
| drawing the geometry | ~2 ms |

Both ran on **every repaint**, because the strip re-reads the colouring every
frame — colouring is a command with no change signal. `_draw` is **1.9 ms** now.

- `_ca_rgba` is array code: a `searchsorted` for the atom→residue map, bincounts
  for the sums, and `np.unique` on a stable order for "the first CA wins".
- Its structure-derived half is cached separately from its result, because only
  the *colours* change per frame — uppercasing 234k atom names is 50 ms on its
  own.
- **`res_ids` is not unique**, and that is a real defect this work did not fix:
  an integrative model numbers residues within each chain, so the pore has
  234,184 slots carrying **1,667 distinct ids**, and the map keeps whichever slot
  comes *last*. Almost every residue therefore projects to NaN. The rewrite
  reproduces last-wins exactly so that a change for speed is only that; see
  [known-issues](/references/known-issues.md).

**The caching mistake worth not repeating: identity is the wrong key here.**
The vertex buffers next door are keyed on array *addresses*, which is sound
because the scene builder replaces arrays. The colour arrays are **re-derived in
place**, so identity survives a change it must not survive — keyed that way,
6.2 % of a render sheet came back rainbow where it should have been grey,
carrying `spectrum count` over from the previous scene. It was visible only in
the image; the percentage on its own said nothing. They are keyed on a content
hash now, which costs ~3 ms and is paid ten times a second because the chrome is
throttled, not sixty.

**Nothing is left in the frame but a matrix.** Vertex buffers, the overlay
texture, and — last — the uniform buffers and bind groups, which were still
being allocated per object per frame to carry two hundred bytes. They are pooled
by draw position and rewritten with `write_buffer`; a pool indexed by position
needs no invalidation, since the worst a stale slot can do is be overwritten.

**The interactive frame was 66 % chrome.** Rotating a quarter-million-bead model
cost 21 ms a frame at a Retina viewport, and the molecule was the smaller half of
it: 9.6 ms rasterising the panel, the sequence strip and the labels, plus 4.2 ms
uploading that 12.9 MB image, plus 7 ms rebuilding an interleaved vertex array
that had not changed and 2.4 ms re-uploading it. Three caches, all in
`wgpu_backend` and `wgpu_view`, took the frame to **1.7 ms** — and the rendered
sheet is byte-identical to the reference, max channel difference 0.

- **The vertex buffer** is cached per geometry, keyed on the *addresses* of its
  arrays rather than their contents: the scene builder makes new arrays whenever
  anything changes, so an address is a sound identity and hashing tens of
  megabytes a frame would cost more than the work it saves. The entry holds the
  geometry, so its `id` cannot be recycled underneath it.
- **The overlay texture** is cached on a sampled signature of the image, not a
  hash — a full hash of 12.9 MB every frame costs more than the upload.
- **The chrome image is repainted on a timer, not a dirty flag**, and that is the
  whole design. A dirty flag here has a known failure mode, written into the
  function it replaces: the panel re-reads the sequence colours every frame
  because colouring is a *command* with no signal, so a cache invalidated by the
  events anyone thinks of goes stale on the one they did not. A timer cannot go
  permanently stale — worst case the panel is 100 ms behind, and it corrects
  itself. GUI interaction calls `invalidate_chrome()` so a click still feels
  immediate, and a scene with 3-D labels is painted every frame as before,
  because labels move with the camera.

**Two test bugs that only exist at a device pixel ratio above 1.** `test_wgpu_view`
compared `scene_origin_y()` against `_height - scene_height()` — the framebuffer
height against a widget height — and divided a widget width by the ratio to
predict a projection that answers in widget pixels. Both are invisible on a 1x
display and off by exactly 2x on a Retina one. This is the third time today the
two pixel sizes in this widget have produced a wrong answer that looked like a
real difference; the others were a render comparison and a leaf-size sweep.

**And a test that had been red for two commits without being run.**
`test_wgsl_parity` globbed every `.wgsl` in the directory and prepended the
*render* prelude to each, which stopped being true the moment compute shaders
moved in — `raytrace.wgsl` was being concatenated with the shading model and
declaring a second `fn shade`. The shader families are now written out
explicitly, with a test that fails if a new shader is not classified.

**`GpuVolume` is what removed the transport.** Every one of those kernels
already ran on the GPU; the *grid* did not stay there. `volume_ops.wgsl` does the
threshold, the scale and the root in place so the SES seed and the unit
conversion never touch the host, `mc_active.wgsl` reports each crossing's **case**
alongside its cell so the host never reads the grid back to recover it, and
`mc_vertices.wgsl` both places each welded vertex on its edge and samples the
gradient there — replacing `numpy.gradient` over the whole volume plus a
host-side trilinear sample, which was 31 ms of a 107 ms marching cubes spent
building three 8 MB arrays to read a few tens of thousands of values out of.

**Two defects that came out of building it, both silent:**

- **The transform's seed has a direction and it is easy to get backwards.**
  `forbidden = distance < probe` is where the probe *cannot* reach, and the
  transform measures out of the region it *can*, so the seeds are the reachable
  voxels. Inverted, nothing fails — the surface *grows*, 46,558 vertices where
  there should be 42,562. The test pins the counts exactly, because they are
  combinatorial and an `allclose` would shrug at it.
- **The crossing buffer was sized on a guess.** A quarter of the cells is
  "generous" for a closed surface and an SES field at coarse spacing beat it; the
  scan then returned `None` mid-chain and the host fell through to a CPU path
  holding no grid at all. It retries at the exact count the shader reported now,
  and the fallback reads the volume back rather than crashing on `None`.

**One spatial index, built in NumPy, shared by the field kernels.** A uniform
grid whose cell is the query radius, so 27 cells is provably enough. Building it
is a sort and a prefix sum.

**`bvh.wgsl` is a prelude, not a copy.** `raytrace.wgsl` and `bvh_probe.wgsl` are
both that file plus an entry point, which is what makes the probe worth having:
`test_bvh.py` compares the *same* `closest_hit` the tracer runs against an
exhaustive Python search, so the tree is tested rather than the picture.

**There is deliberately no CPU ray tracer.** chimol's renderer is WebGPU, so a
session that can display a molecule can trace one; `NoComputeDevice` is raised
rather than falling back. A second shading implementation would be a large body
of code nothing ever runs — which is exactly how the previous pure-NumPy twin
came to be silently broken while every test passed.

**What stays on the CPU, on purpose.** The neighbour counts, the bond pairs and
the marching-cubes topology, because those must be exact and integer and an f32
route would differ by one at a boundary. The density splat, because 14 ms is not
a bottleneck. And `nearest`, which the k-d tree already answers and which is now
computed only where the weight sum is zero — on a normal surface, no work at all.

**Traps, each of which first read as "the GPU is not worth it":**

- **Compile the shader once.** Creating the module and pipeline per call made the
  distance grid **2.4× slower than the CPU route** — the measurement included the
  compiler. Cached by source and binding shape now.
- **A ring scan needs a horizon.** A voxel in an empty bounding-box corner is
  60 Å from the nearest atom, so the "everything unsearched is at least `r·cell`
  away" bound needs fifteen rings. Both routes clamp at 8 Å, so they agree by
  construction; 8 Å with a 6 Å cell won over all eight combinations measured.
- **The first dispatch of a process pays ~730 ms of shader compilation.** Once,
  and only if a surface is built — but never benchmark a single build.
- **A cell must be larger than the step it is walked in.** The shadow kernel lets
  one ray step claim each occluder (`floor(along / step)`); with cell = step that
  claim was sometimes unreachable, because the light is not axis-aligned and the
  displacement can be a full `step + reach` on every axis at once. It dropped 20
  vertices out of 40k — nothing in the mean, 0.39 out of 1.0 where it hit.
- **Do not swallow a shader compile error.** The kernels return `None` to mean
  "hand this back to NumPy", which is right for *no adapter* and catastrophic for
  *this shader does not compile*: a broken kernel then passes the whole suite as
  a silent CPU fallback. `compute.ShaderError` is re-raised by every kernel. Two
  reserved-keyword collisions (`meta`, `active`) were found this way.
- **Read back only what was written.** The marching-cubes scan allocated one
  output slot per cell (8 MB) and read all of it; sized to a fraction and read as
  a counter-then-prefix it is a third of that — and still not enough to pay for
  the upload, which is the finding above.

`compute.backend` in `chimol_display.json` (display-config **version 13**) is
`auto` / `gpu` / `cpu`, and `CHIMOL_COMPUTE` overrides it — which is what makes
the parity tests possible, since they run the *public* entry point twice with
each side forced.


# Kernel routing

numba does not exist in Pyodide, and the cheap answer is dead: a no-op `njit` shim
(exactly `NUMBA_DISABLE_JIT=1`) is **300–680× slower** — `count_within_radius` on
hGBP1 goes 6.7 ms → 3,516 ms, the 64³ EDT 9.6 ms → 6,496 ms. mypyc cannot rescue it
either: **1.04×** on numpy code (measured on `_edt_1d_sq`), because it unboxes
Python natives and cannot see a numpy buffer, so `arr[i]` stays a
`PyObject_GetItem`. The same ceiling binds every whole-program Python→WASM compiler.
Route each kernel, cheapest first:

1. **Web config defaults** — `surface_quality`, grid spacing, cartoon subdivision,
   AO samples are already config values; a `web` profile is a JSON change.
2. **WGSL compute** for the data-parallel ones. Measured: distance grid **229×**,
   marching cubes 4–19×.
3. **scipy's compiled routines** where an exact equivalent exists — `cKDTree`
   (19.6 ms vs numba 6.7 ms), `ndimage.distance_transform_edt` (32.6 ms vs 9.6 ms).
   3–6× off numba is nothing for one-shot scene construction, and scipy ships
   compiled in Pyodide.
4. **Pythran, then C99, both `-msimd128`.** Pythran first: it is numpy-aware and
   compiles from a *single annotated Python source*, so unlike C it does not create
   a second implementation.
5. **Bake server-side** — the permanent escape hatch.

**A CPU route is mandatory for every GPU kernel**, because standalone HTML opened
from `file://` may have no WebGPU adapter.

# What the baseline capture itself found

Four defects, three of them in the capture path and one in the renderer. Each is
worth more than the images, because each made a wrong answer look right.

- **`shoot()` ignored `QImage.save()`'s return value.** The disk filled mid-run,
  8 of 20 scenes were never written, and every one of them printed `[ok]`. Now
  `screenshot.py:_save` raises on a null image, a failed write, or a file that
  comes back implausibly small.
- **A restored dock layout handed the 3-D view a 1280×90 strip**, so the molecule
  was a speck under a full-width sequence bar. A pixel floor does not catch this —
  a strip is wide. `screenshot.py:assert_view_usable` now checks size *and*
  aspect and refuses; it fired on the second structure for real. Root cause fixed
  by pointing `CHISURF_SETTINGS_DIR` at a scratch dir, and by pumping the event
  loop until the viewport settles rather than once.
- **Scenes leaked state into each other.** The first space-fill baseline came out
  rainbow because `spectrum count` from an earlier scene was still in effect —
  which reads as a property of the sphere representation and is not one. Fixed
  with an explicit `RESET` list; keep it in step with what the scenes perturb.
- **A settings scene is unreadable without a matched control.** Diffing
  `silhouette` against `cartoon` said 11.53 % of pixels changed, which looks like
  a working silhouette and was really the colour difference. Against a control
  differing by the setting alone it is **2.08 %**, and the amplified difference
  image shows thin strokes at depth discontinuities — a real outline. *More*
  change would have been the failure, exactly as the earlier FBO work recorded.

The renderer defect — ambient occlusion applied when it is switched **off** — is
written up in [known-issues](/references/known-issues.md) and deliberately not
fixed in the same change, because fixing it changes what the renderer draws and
would invalidate the baselines being captured alongside it.

# Traps found so far

- **The surface format is `rgba8unorm-srgb`.** WebGPU's preferred format is sRGB;
  chimol's GL writes to a non-sRGB default framebuffer. Every colour will wash out
  if this is not handled explicitly. Caught only by looking at the image — a clear
  value of 0.09 came back as 85, not 23.
- **`chimol/__init__.py` eagerly imports `MolView`**, so importing *any*
  `chimol.geometry` submodule drags in Qt *and* `chisurf`. Bypass it by registering
  `chimol`/`chimol.geometry` as `types.ModuleType` with `__path__` set.
- **numba's on-disk cache is keyed to the `chisurf.` module path**, so a JIT
  baseline taken outside the full `PYTHONPATH` dies inside `pickle.loads` with a
  `ModuleNotFoundError` that looks nothing like a cache problem. Use a fresh
  `NUMBA_CACHE_DIR`.
- **Do not verify mesh equality by sorting rounded centroids.** f32-vs-f64
  interpolation flips ties, the sort order changes, and a correct kernel reports
  `DIFFER` at 64³ and 96³ while matching at 48³. Compare order-independent
  summaries instead — total surface area, centroid, bounding box.
- **Offscreen `canvas.draw()` includes a full GPU→CPU readback**, so frame timings
  taken that way measure the readback, not the render.

# Side-finding, worth fixing regardless

`geometry/surface.py::_compute_distance_grid_nb` is brute force — O(voxels × atoms)
with no spatial acceleration. On hGBP1 at 96³ that is **35 seconds** on the desktop
today (8.2 G distance evaluations). Same shape as the raytracer's missing BVH: a
speedup that large is usually a complexity class, not a constant. The GPU port makes
it moot for this kernel, but it should not hide it.

# Related

- [specs/chimol](/specs/chimol.md) — the target: command-compatible with PyMOL and
  better than it.
- [plugins/pymol-parity](/plugins/pymol-parity.md) — the measured PyMOL gap. Needs a
  "web" column for what the browser backend does not do.
- [prds/prd-83](/prds/prd-83.md) — retire pyqtgraph; chimol is PyOpenGL, not
  pyqtgraph. This concept supersedes its rendering direction.
- [prds/prd-37](/prds/prd-37.md) — transport security. Gates the remote-session use
  case: a browser cannot speak ZMQ, so that needs a WebSocket transport, and
  `chisurf/server/transport/zmq.py` refuses non-loopback until CURVE/ZAP lands.
