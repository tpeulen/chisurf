# The molecular surface — HANDOVER

**Branch:** `development` · the work described here is **uncommitted** in a
**shared working tree** — other agents hold their own edits in the same files,
so read §6 before you commit anything.

There are now two ways to compute a molecular surface in chimol, and this is the
brief for the new one: a screen-space Gaussian surface that allocates no grid
and builds no mesh. It renders (picture below), it has real relief, and it is
not finished.

The durable record is [`okf/plugins/chimol-web.md`](okf/plugins/chimol-web.md);
this file is the entry point to the surface half of it.

---

## 1. Why there are two

The meshed surface is a pipeline: density grid → iso threshold → distance
transform → marching cubes → per-vertex colour and occlusion. On T4 lysozyme
(1,363 atoms) it costs **253 ms** and produces **27,920 vertices / 18,610
triangles**, and every one of those numbers is paid again whenever anything in
the scene changes. Profiled, that 253 ms is:

| stage | cost |
|---|---:|
| `_splat_field` — the 3-D Gaussian density grid, in NumPy | 106 ms |
| marching cubes | 63 ms |
| ambient occlusion over the mesh vertices | 65 ms |
| assembly, colour, normals | ~20 ms |

That is the right answer when the deliverable is **geometry** — an OBJ to
export, a volume to measure, a mesh for the ray tracer. It is the wrong answer
for turning a structure with the mouse, which is what the 3-D view is for.

So the surface gained a **quality** setting, and its fastest level is a
different algorithm rather than a coarser setting of the same one.

## 2. What exists now

### The levels — `renderer/surface_quality.py`

| level | how | build | vertices |
|---|---|---:|---:|
| `splat` | screen-space Gaussian, no grid | ~1 ms | 0 (1,363 instances) |
| `fast` | mesh, 0.9 Å grid | ~90 ms | ~8,000 |
| `balanced` *(default)* | mesh, 0.5 Å grid | ~250 ms | 27,920 |
| `fine` | mesh, 0.35 Å grid | ~700 ms | ~60,000 |

`apply_surface_quality` returns a **copy** of the `surface` section with only the
level's keys replaced — the live display config must not be written to, or the
next rebuild reads the level's spacing as though the user had chosen it. An
unknown level leaves the config alone rather than falling back: the setting is a
string someone types, and the surface they already had beats a surface at some
other resolution.

Set it with `set surface.quality, splat` (or `fast` / `balanced` / `fine`).
Other new settings: `surface.splat_decay` (2 is a soft envelope, 5 hugs the
atoms), `surface.splat_iso` (where the resolve cuts), `surface.splat_scale` (a
multiplier on the atom radii).

### The splat — two shaders and two passes

- **`wgsl/gauss_splat.wgsl`** — one camera-facing quad per atom, blended
  **additively** into an offscreen target. Two attachments:
  - `rgba16float`: premultiplied colour (`rgb`) and density (`a`);
  - `r16float`: density-weighted **view depth**.
- **`wgsl/gauss_resolve.wgsl`** — one fullscreen triangle. Cuts at the iso
  level, reconstructs the surface depth as `depth_sum / density`, takes the
  normal from *that* height field, and shades through the shared `shade()` so
  the surface obeys the same light rig as everything else in the scene.
- **`renderer/wgpu_backend.py`** — `_build_gauss_pipelines`, `_gauss_field_view`,
  `_accumulate_gauss`, `_resolve_gauss`, a `"gauss"` branch in `pipeline_for`,
  and the two passes wired into `render_into` (accumulate after the main pass,
  resolve at the head of the second pass, before the silhouette and the chrome).
- **`renderer/view.py::_build_surface_splat`** — emits
  `Geometry(kind="gauss", ...)` with the same per-instance layout the sphere
  impostors use, so nothing had to be repacked.
- **`wgsl/shading.wgsl`** — the shared uniform block gained
  `gauss : vec4<f32>` (decay, iso, opacity, depth normalisation), so
  `UNIFORM_FLOATS` is `4*16 + 7*4`.

## 3. The three things that cost real time

1. **A density gradient has no shape.** The obvious resolve — the one in every
   write-up of this technique — takes the normal from the screen-space gradient
   of the *density*. Inside the molecule the density saturates, its gradient
   goes to zero, and what you get is a correct silhouette with a lit rim and a
   flat grey interior. It looks like a bug in the lighting and it is not. The
   fix is the second attachment: accumulate density-weighted depth, divide it
   out, and differentiate **that** — a height field is exactly what a
   screen-space normal is correct for.

2. **`r32float` is not blendable.** wgpu refuses the pipeline outright:
   *"Color state [1] is invalid — Format R32Float is not blendable"*. The depth
   channel must be `r16float`, and 16 bits then forces the normalisation:
   a depth of a few hundred scene units times a density of tens overflows
   float16's 65,504 on anything larger than a peptide, and the overflow shows as
   a surface whose middle is inside-out. So the splat writes
   `front * u.gauss.w * density` and the resolve divides `u.gauss.w` back out.
   `u.gauss.w` is `1 / (4 * target_radius)`.

3. **A splat stands for a sphere, so it must write the sphere's front.**
   `front = depthView - radius * sqrt(1 - r²)`. Accumulating the atom *centre*
   depth puts the surface half a radius inside every atom, and the result reads
   as a smoothed centroid cloud rather than an envelope.

One smaller trap, in `render_into`: `opacity`, `two_sided` and friends are
per-draw locals inside the object loop. The Gaussian block runs after that loop,
and reading them there reads whatever the last object happened to set.

## 4. What is missing — do these next, in order

1. **The surface has no depth of its own.** It is resolved in the second pass
   with no `frag_depth`, so it draws over the cartoon and the sticks rather than
   intersecting them. The depth is *already accumulated* — the resolve knows the
   surface's view z — so this is: write `frag_depth` from the reconstructed
   depth, give the resolve pipeline a depth attachment, and move it into a pass
   that has one. Until then `splat` is honest only as the sole representation.
2. **Two guard tests will fail and have not been run.**
   `test_wgsl_parity.py::TestWgslSource::test_every_shader_is_classified` needs
   `gauss_splat.wgsl` and `gauss_resolve.wgsl` in its `FAMILIES` table (both are
   `"render"`), and `test_gpu_seam.py` checks every constant in
   `renderer/gpu/enums.py` against the binding — `TextureSampleType.unfilterable_float`
   was added for the `r32float` attempt and is **now unused**. Remove it or
   confirm the binding agrees.
3. **No tests at all for the new path.** The shape they should take is
   `test_impostor_primitives.py`: routing and packing without a GPU, then a
   rendered frame with the GPU-skipping fixture. Worth asserting: a `gauss`
   geometry routes to the `"gauss"` pipeline; `apply_surface_quality` copies
   rather than mutates and leaves an unknown level alone; the resolved frame is
   *not flat* (the whole point of §3.1 — compare the variance of the interior
   against the rim, or the two images will differ by nothing a threshold can
   see).
4. **The before/after pair is half-taken.** `surface_splat.png` exists; the
   meshed one at the same camera does not, and capturing it is what makes the
   comparison reviewable later. Same script, without the `set` (see §5).
5. **Graininess.** The relief carries visible per-texel noise from the 16-bit
   depth quantisation. A wider stencil or a small blur of the depth channel
   before differencing is the cheap fix; do it after the depth output, because
   that changes what is being differentiated.
6. **The browser has not run this.** `rgba16float` and `r16float` as *blendable*
   render targets are the question; if either is not, the browser needs a
   fallback level rather than a broken surface. `test_browser_render.py` is the
   place — it already types commands at the page.
7. **The meshed levels are still all-NumPy where they need not be.** The 106 ms
   density grid is the same shape as `distance_grid.wgsl`, which is already a
   compute kernel with a router entry. That is the next real speed-up for
   `fast`/`balanced`/`fine`, and it is independent of everything above.

## 5. How to look at it

The scene builder and the renderer both work headlessly; no window server is
needed. From the repository root, in the `arm64` env:

```python
import sys; sys.path.insert(0, "chisurf/plugins/chimol")
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from PIL import Image
import numpy as np
from chimol.cmd import Cmd
from chimol.renderer.headless import SceneSink
from chimol.renderer.pack import pack_scene
from chimol.renderer.view import MolView
from chimol.renderer.wgpu_backend import WgpuMeshRenderer
from chimol.web.demo import BrowserHost, demo_pdb_path

view = MolView(renderer_factory=SceneSink); view._renderer.resize(800, 640)
cmd = Cmd(BrowserHost(view))
cmd.do(f"load {demo_pdb_path()}")
cmd.do("set surface.quality, splat")     # or fast / balanced / fine
cmd.do("as surface"); cmd.do("orient")

sink = view._renderer
image = WgpuMeshRenderer(800, 640).render(
    pack_scene(sink.scene), sink.get_view_state(),
    background=(0.16, 0.16, 0.16),
    target_radius=getattr(sink, "_target_radius", None),
)
Image.fromarray(image).save("surface.png")
```

Run it with
`QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=$(mktemp -d) PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:."`.
**Use a fresh settings directory**: a persisted layout or a stale
`chimol_display.json` will silently give you a different quality level than the
one you set, and the picture will be right for the wrong reason.

**Always look at the PNG.** Every one of the three findings in §3 was invisible
in the numbers and obvious in the image; two of them produced a *plausible*
picture that was wrong.

## 6. Committing this in a shared tree

`renderer/view.py`, `config.py` and `chimol_display.json` carry **another
agent's uncommitted work** as well as this — a mouse-selection-mode change
across `view.py`, `mouse_modes.py`, `internal_gui.py` and `menu_bar.py`, and
their own display-config migrations (they hold versions 16 and 17; the surface
work has not taken a version at all yet).

So do not `git add` those three files. Build the blob from `HEAD` plus your own
hunks and commit through a temporary index — the recipe used for the last three
commits in this area:

```bash
export GIT_INDEX_FILE=$(mktemp -u)
git read-tree HEAD
git add <only-your-own-new-files>
blob=$(git hash-object -w /path/to/your/version/of/view.py)
git update-index --cacheinfo 100644,$blob,chisurf/plugins/chimol/chimol/renderer/view.py
git commit -F -
```

Then `git add` the same paths in the *real* index so it does not report your
committed files as deletions. Never `reset --hard`, `checkout --`, `clean -f`,
`stash`, `--force`, `add -A` or `commit -a`; `okf/log.md` and `CHANGELOG.md` are
append-only from several agents at once, so build those from `HEAD` too rather
than from the working copy.

## 7. Files

| file | state |
|---|---|
| `renderer/wgsl/gauss_splat.wgsl` | new |
| `renderer/wgsl/gauss_resolve.wgsl` | new |
| `renderer/surface_quality.py` | new |
| `renderer/wgpu_backend.py` | modified — pipelines, targets, the two passes, `gauss` uniform |
| `renderer/wgsl/shading.wgsl` | modified — `gauss : vec4<f32>` in the shared block |
| `renderer/view.py` | modified — `_build_surface_splat`, the quality branch |
| `renderer/gpu/enums.py` | modified — `unfilterable_float`, now unused (§4.2) |
| `chimol_display.json`, `config.py` | modified — `surface.quality` and the splat settings |
