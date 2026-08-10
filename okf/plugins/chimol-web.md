---
type: Plugin Concept
title: ChiMOL in the browser — one WGSL codebase
description: ChiMOL must also run in a web page embedded via JavaScript. WebGPU is the only graphics+compute API spanning macOS desktop, Linux/Windows and the browser, so desktop and web share one WGSL source.
resource: chisurf/plugins/chimol/
tags: [plugins, structure, viewer, webgpu, wgsl, web, pyodide, compute]
timestamp: '2026-08-10T00:00:00Z'
---

# HANDOVER — start here (2026-08-10)

**Goal.** ChiMOL must run in a browser embedded via JavaScript. WebGPU is the
only graphics+compute API spanning macOS desktop, Linux/Windows and the browser,
so desktop and web share **one WGSL source** rather than maintaining two
renderers, two shader dialects and two copies of every kernel. Phases 0 and 1 are
done; Phase 2 (replacing the desktop OpenGL renderer) is part-built.

**Environment.** Run everything in the `arm64` conda env with
`PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:."`.
`wgpu` 0.32.0 and `rendercanvas` 2.7.2 are pip-installed there but **not declared**
— the chigame agent owns `pixi.toml`/`pyproject.toml` and is adding them; do not
edit those two files, coordinate on the agent board.

**The one command you need.** Every remaining feature is accepted or rejected by
looking at a GL|WGSL pair:

```
QT_QPA_PLATFORM=offscreen python -m chisurf.plugins.chimol.test.compare_wgsl \
    cartoon sticks surface transparency
```

It writes `chimol/test/renders/wgsl/compare_sheet.png`, one row per scene,
GL on the left and WGSL on the right. Baselines and their cameras live in
`chimol/test/renders/gl_baseline/` (23 scenes, `manifest.json`).

**USER RULES, both learned the hard way this session:**
1. **Always produce PNGs.** Never report a rendering result as an IoU, a mean
   brightness or a table of RGB values. Three times a scalar pointed the wrong
   way and the picture settled it in seconds. Send images with `SendUserFile`.
2. **The WGSL look is the target, not the baseline.** The user judged it better
   than the OpenGL render. Do not tune the material back toward GL. Parity means
   *feature inventory* — every representation, setting and cue present and
   controllable — not pixel agreement.

## Do these next, in order

1. **Metaball: "not flubber enough" (user request, untouched).** There is **no
   metaball scene in the baseline**, so there is nothing to judge against — add
   one to `SCENES` in `test/capture_gl_baseline.py`, re-capture (the capture now
   takes scene names, so this costs one scene and leaves the other 23 alone),
   *then* tune. Existing knobs in `chimol_display.json`: `sigma_factor 4.0`
   (fusion — merges beads into smooth lobes, the main lever), `alpha 0.55`,
   `shininess 96`, `specular_strength 0.85`, `rim_strength 0.55`,
   `iso_value 0.1`. Prior tuning is recorded in
   [pymol-parity](/plugins/pymol-parity.md): 9.0 sigma was tried and rejected as
   "a featureless egg", so the useful range is narrow.
2. ✅ **Done — "white-background darkness" was a contaminated baseline.** See
   *The bug that was not in the renderer* below; the four affected baselines are
   re-captured and `compare_wgsl bg_white bg_grey_spectrum cartoon
   nucleic_cartoon` now matches on all four rows.
3. **Impostors.** Sphere and capped-cylinder impostors were prototyped and proven
   in Phase 0 (148L at **2 triangles/atom** with per-fragment depth, reusing the
   raytracer's own analytic capsule intersection) but are **not yet in
   `wgpu_backend.py`**, which draws only `kind == "mesh"`. Wiring them in is the
   biggest single visual win: the tessellated sphere path costs 374,112 triangles
   on 148L against ~2,770.
4. **Remaining features**, each with a `compare_wgsl` pair: depth cue/fog,
   silhouettes, labels (`kind == "text"`, currently skipped entirely).
5. **Then embed in the Qt dock.** `rendercanvas`'s `QRenderWidget` is verified
   embeddable under PyQt5 (870×485 in a real dock layout). Only after that does
   `qtgl.py` get retired.

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
- **Suspect the baseline, not only the renderer.** A leaked setting does not
  announce itself; it looks like whichever renderer you trust less, and the
  baseline is the half nobody re-derives. Before spending a day inside a shader,
  render the *same* scene both ways with the suspected setting forced each way —
  three panels, one image, one minute.
- **Compare order-independent summaries** (area, centroid, bbox) for meshes, not
  sorted rounded centroids — f32-vs-f64 flips ties and reports a correct kernel
  as wrong.

## Session commits

`0b90174d9` Phase 0 gates · `58996c37c` GL baselines · `58db3aea4` AO switch fix ·
`756e2df06` settings-kind test · `fa7377580` SceneSink · `79b3d6811` pack.py ·
`128cc86ab` WGSL renderer · `78780b602` scene_rect · `2842d8e30` is_empty fix ·
`ee39098a6` compare harness · `6464a2274` transparency + background

# Detail and history

# Where to pick this up (earlier, superseded by the handover above)

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
