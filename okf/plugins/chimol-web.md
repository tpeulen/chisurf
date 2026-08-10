---
type: Plugin Concept
title: ChiMOL in the browser — one WGSL codebase
description: ChiMOL must also run in a web page embedded via JavaScript. WebGPU is the only graphics+compute API spanning macOS desktop, Linux/Windows and the browser, so desktop and web share one WGSL source.
resource: chisurf/plugins/chimol/
tags: [plugins, structure, viewer, webgpu, wgsl, web, pyodide, compute]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

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
3. **Phase 2 — the desktop WGSL renderer**, feature by feature, each proven by a
   screenshot pair against the captured GL baseline.

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
