# ChiMOL — HANDOVER

**Branch:** `development` · all commits **local** (never push) · shared working tree,
so other agents have uncommitted edits in the same files — see §7.

ChiMOL now runs in a **browser**, on the browser's own WebGPU, from the same Python
and the same nineteen WGSL files as the desktop. This is the brief for whoever
picks it up.

The durable record is [`okf/plugins/chimol-web.md`](okf/plugins/chimol-web.md);
this file is the entry point to it.

---

## 1. Where it stands

The desktop engine was made portable, then pointed at a browser. Four phases, all
landed:

| | what | proof |
|---|---|---|
| A | engine imports no Qt | 21 modules import under a Qt-blocking finder |
| B | engine names no GPU binding | nothing outside `renderer/gpu/native.py` imports `wgpu` |
| C | chrome is GPU quads | `QPainter` 2.94→10.06 ms across viewport sizes vs a flat ~1.4 ms; 33 MB → 107 KB uploaded |
| D | `platform`/host split + guard | `test/test_engine_is_portable.py` |

Then the browser itself: `renderer/gpu/browser.py`, `chimol/web/`, and a demo that
draws **148L as 1363 sphere impostors with ambient occlusion**, plus the panel,
with the mouse working — drag rotates, wheel zooms, panel clicks open menus.

**One engine.** There is no JavaScript renderer and there must not be one:
`boot.js` is a loader with no pipeline, no buffer and no draw call, and a guard
test forbids them. Every frame is Python.

## 2. How to run it

```bash
csg_chimol_web                       # packs, serves, opens the browser
python -m chisurf.plugins.chimol.chimol.web.serve --no-open --port 8781
```

A busy port is handled: it detects chimol already serving there and opens that,
or steps to a free port and says which.

**Drive the page with Playwright, not the Chrome tools.** The browser tools reach
a Chrome that is *not on the same host* as the shell — a server answering `200`
to `curl` gives it `ERR_CONNECTION_REFUSED`, and every read lands on
`chrome-error://chromewebdata/`, which is also why `navigator.gpu` reads false.
Playwright's Chromium runs in the same sandbox and works with
`--enable-unsafe-webgpu`.

```bash
pytest -m slow chisurf/plugins/chimol/test/test_browser_render.py
```

Environment: the `arm64` conda env, `QT_QPA_PLATFORM=offscreen`,
`PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:."`.

## 3. Do these next, in order

### 3.1 Selections must work without Qt

`renderer/view.py::_update_selection_highlight` (`:8898`) builds the marker
geometry and lives in the **Qt widget**, so the browser has no path to it and a
sequence-strip selection highlights nothing in 3-D. Move it beside the other
scene builders.

**Do not port it as it stands.** The markers set `meta["px_mode"]`, and the WGSL
backend **never reads that flag** — it reads only `size` and `world_radius`
(`wgpu_backend.py:906`), so pixel-mode markers get world-radius behaviour: size
varying with depth, which is the scattered dots in the user's screenshots. Fix
that first or the port carries the bug across. `_selection_marker_width` computes
**pixels**, clamped to PyMOL's 3–10 band, so the units are certain at the
producing end; the open question is what the impostor pipeline does with `size`
when `world_radius` is false.

### 3.2 Delete the Qt sequence dock

`app/sequence_dock.py` duplicates what the in-viewport strip already draws with
quads. Removing it strikes a line from `HOSTS` in `test_engine_is_portable.py`
(16 → 15) and it is the cheapest of the thirteen `app/` panels to close, because
the replacement already ships and is already tested. Check
`app/molview_main_window.py` for its registration and the `Seq` toolbar button.

### 3.3 Neighbour counting on the GPU — measure first

The demo's occlusion is a brute-force `(n, n)` numpy pass and `compute.build_grid`
is numpy, so the only GPU part today is the occlusion integral in
`occlusion.wgsl`.

**The number that shapes this.** Forced with `CHIMOL_COMPUTE=gpu` on 148L's 1363
atoms: the GPU integral is **806 ms against numpy's 39 ms** — twenty times
slower, because `MIN_WORK_ITEMS` is 20 000 and 1363 work items cannot amortise
the dispatch and the buffer round-trip. A GPU neighbour count at that size loses
by *more*, not less: it is cheaper work than the integral it feeds.

The shape that wins is **one dispatch doing grid, count and integral together**
without a round-trip between them, on a structure with tens of thousands of
atoms. A counting sort on the GPU is histogram → prefix sum → scatter;
`bvh.wgsl` already has a prefix sum to copy from. The router already picks by
size, so the same code takes the GPU path automatically once it is worth taking.

### 3.4 The rest of the `app/` panels

Thirteen of `HOSTS`'s sixteen entries are `app/` panels that draw **with Qt
widgets what the in-viewport panel already draws with quads**. So most of that
list closes by moving them into the chrome, not by editing them — which is also
the "~90 % of the app lives in the WebGPU window" that was asked for, now the
same job as finishing the port rather than a separate one.

## 4. Things that are settled — do not re-litigate

- **No second renderer.** A JS renderer would need its own ray tracer, BVH build
  and marching cubes to match the nineteen WGSL files, and every future pass
  would be written twice.
- **`wgpu.backends.js_webgpu` is a stub** (`# NOTE: this is just a stub for
  now!!`), so `rendercanvas`'s pyodide backend has nothing to drive. That is why
  `browser.py` exists.
- **`cerbsim/webgpu`** was read and not adopted: its engine binds one bind group
  unconditionally while `silhouette.wgsl` and `overlay.wgsl` each declare
  `@group(1)`, and its depth texture is not sampleable — which is exactly what
  pass 2 does.
- **The canvas format is never sRGB.** `getPreferredCanvasFormat()` returns
  `bgra8unorm`/`rgba8unorm`; the trap is sprung only by "fixing" it with
  `viewFormats` + `createView({format})`. `configure_canvas` *refuses* sRGB.
- **Named `host`, not `platform`** — a package called `platform` would shadow the
  standard library's, which this repo already paid for with `chisurf/math/`.

## 5. Traps that cost real time

- **Logical vs device pixels.** The panel lays out in *logical/CSS* pixels and is
  scaled to device pixels as the quads are built. Get it wrong one way and it
  draws correctly but ignores every click; the other way and it goes off-screen.
  Both happened. `QuadPainter(scale=...)` is the one place they meet.
- **`hit_test` answers from the last frame's layout.** A resize without a repaint
  tests stale geometry — offscreen, where nothing paints, the block sat at
  `y=-68` on top of the object rows.
- **A Qt-blocking test finder must use `find_spec`.** `find_module`/`load_module`
  was removed in Python 3.12, so a finder written against it is silently skipped
  and every module "passes" with Qt fully available.
- **`QApplication.instance() or QApplication([])` as a bare statement** keeps no
  reference, so it is collected and the next `QWidget` **aborts the interpreter**.
- **Font metrics do not scale linearly.** The atlas is baked at 4×; dividing its
  advance by four gives 8.5 where Qt's 10 pt gives 8. `Atlas.render_scale` exists
  for this.
- **A monospaced font's advance bounds spacing, not ink.** `─` starts a texel
  left of the pen; sized to the advance it bleeds into the neighbouring cell.
- **The suite cannot collect while `chimol/` is on `sys.path`** — chimol has a
  top-level `cmd` package, `pdb` imports the stdlib `cmd`, and pytest's debugging
  plugin imports `pdb` at configure time. A collection error there says nothing
  about the tests.

## 6. What guards what

| test | what breaks it |
|---|---|
| `test_engine_is_portable.py` | a Qt or `wgpu` import creeping back; a stale `HOSTS` entry |
| `test_gpu_seam.py` | a new importer of the binding; a constant drifting from it |
| `test_chrome_atlas.py` | a glyph drawn but not baked (caught `…`); ink on a cell border; a bold face that did not resolve |
| `test_quad_painter.py` | alignment, clipping, gradients — checked with **no GPU**, via `quad_raster.py` |
| `test_chrome_painter.py` | the panel needing a toolkit to import |
| `test_browser_render.py` (`slow`) | the whole browser path, asserting the **molecule**, not just that something drew |

## 7. Shared working tree

Other agents hold uncommitted edits in these same files. Never
`reset --hard`/`checkout --`/`clean -f`/`stash`/`--force`/`add -A`/`commit -a`.
Commit only your own paths; if a file has concurrent edits, build the blob from
`HEAD` plus your hunk rather than adding the working-tree file — `okf/log.md` lost
an entry that way and briefly gained a duplicate when two agents restored it at
once. No commit trailers.
