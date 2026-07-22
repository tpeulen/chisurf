---
type: Plugin Profile
title: ChiMOL molecular viewer plugin
description: OKF profile for the ChiMOL structure viewer — PyMOL-style command surface and a Qt-free renderer abstraction.
resource: chisurf/plugins/chimol/
tags: [plugins, structure, viewer, cmd, renderer]
timestamp: '2026-07-06T00:00:00Z'
---

# Identity

| Field | Value |
| --- | --- |
| Plugin id | `chimol` |
| Display name | `Structure:Structure:ChiMOL` |
| Categories | `Structure`, `Molecular Viewer` |
| Version | `0.2.0` |
| Package | `chisurf/plugins/chimol/chimol/` |
| History | Formerly `moview` / ProtView; renamed to `chimol`. |

ChiMOL is an in-tree molecular viewer with a PyMOL-compatible `cmd` command line,
a `chimol-cli` script (see [Macros, CLI & scripting](/subsystems/macros-cli.md)),
and a renderer abstraction designed so the controller and scene stay GUI-free.

# Command surface (`cmd`)

The command layer (`chisurf/plugins/chimol/chimol/cmd/`) mirrors a subset of the
PyMOL `cmd` API and is grouped by concern: `core`, `command`, `loader`,
`rendering`, `selection`, `sele_parser`, `measurements`, `editing`, `exporting`,
`animation`, `lifecycle`, `rmf`. Parity is tracked against PyMOL in tiers; the
following are implemented:

- **Shell & IO** — `@script` execution, `help`/`load`/`open`/`fetch`,
  `objects`/`get_names`, error routing.
- **Camera verbs** — distinct `center` / `orient` / `zoom` / `reset` semantics.
- **Color** — modes plus `byelement`, `bychain`, `spectrum`, and named colors;
  per-selection RGBA overrides.
- **Selection grammar** — `sele_parser.py` is a recursive-descent
  tokenizer + AST parser + evaluator supporting `all`/`none`/`resi`/`resn`/
  `name`/`chain`/`elem`/`and`/`or`/`not`/`within`/`around`/`byres`/`expand` and
  `/object/chain/resi/name` macro syntax; integrated into the selection mixin.
- **Per-atom representations** — `ball_mask` / `sticks_mask` are per-atom masks,
  so `show sticks, name CA` and `hide spheres, resi 1-20` work at atom
  granularity.
- **Measurement overlays** — `distance` / `angle` / `dihedral` create persistent
  3D overlays (dashed lines + floating value labels) via a `SceneObject`
  `kind="text"` geometry, not console-only strings.

Known remaining gaps (higher PyMOL tiers): boolean-rich per-object `set`/`get`
coverage, chemistry-light editing (`bond`/`h_add`), volume/map objects, and the
movie/animation and analysis (`align`/`super`/`rms`) systems are only partially
present. Keep unimplemented command names registered so the CLI emits a friendly
"not yet implemented" message instead of `KeyError`.

# Renderer abstraction (design contract)

`chisurf/plugins/chimol/chimol/renderer/` separates a Qt-free scene/controller
from swappable backends. These constraints are **load-bearing** — hold them when
touching viewer code:

1. **No Qt in controller code.** The `MolView` controller and its
   selection/rendering/measurement mixins must import without a `QApplication`.
2. **`scene.py` stays Qt-free.** `Geometry`, `SceneObject`, `Scene` are plain
   dataclasses — the shared contract every backend consumes.
3. **All overlays go through `SceneObject(kind="text", ...)`.** Both the Qt/GL
   (`qtgl.py`) and offline (`raytracer.py`) backends render from the same scene.
4. **`qtgl.py` is a thin translator.** Camera math, shader uniforms, and event
   handling are its only Qt-specific parts; do not add business logic there.
5. **Avoid `QPainter.begin(self)` inside `paintGL`** — it is fragile and slated
   for removal; do not add new uses.

The documented long-term direction is a **Dear ImGui backend** (`imgui-bundle`,
which can coexist with Qt in-process) implementing the `Renderer` ABC, replacing
the hand-rolled `QLineEdit` command bar and `QPainter` label overlays and making
headless rendering/testing straightforward. Future camera state is to be
extracted into a `CameraState` dataclass. No ImGui backend exists yet; the
constraints above exist so that migration stays cheap.

## Mesh-builder performance

Camera rotation/pan does **not** rebuild the scene — `qtgl.py`'s mouse handlers
only update azimuth/elevation and call `update()`, re-rendering the cached
`Scene`. Mesh-build cost is therefore paid on load, representation toggles, and
each trajectory frame, and lives in the geometry kernels, not the paint loop.

Those kernels were per-element Python loops whose dominant cost was
`numpy.cross` (its `moveaxis`/axis-normalisation overhead swamps the arithmetic
when called per point). They are now batched NumPy:

- `primitives._build_stick_mesh` — one `_rotations_from_z` (batched Rodrigues)
  + einsum over all bonds instead of a per-bond loop (~10×).
- `cartoon._extrude_shape` — broadcast the cross-section over all path points and
  the quad-index pattern over all rings (~20×).
- `cartoon._sample_path` — vectorised Catmull–Rom via the Hermite basis (~100×).
- `cartoon._build_frames` — batched cross products; only the sign-continuity flip
  stays a scalar loop (it is genuinely sequential) (~30×).

Net: a full cartoon+atoms+sticks build for a ~18k-atom model dropped ~2.7 s → ~0.4 s.
`_batch_cross` (explicit component form) replaces `numpy.cross` in the hot paths.
**When editing these kernels, keep the parity tests in
`test_geometry_vectorized.py` green** — they pin each vectorised builder against a
reference loop so a change can't silently alter rendered geometry.

The **atoms (balls)** representation merges one sphere mesh per atom. The sphere
was a 16×32 UV sphere — **512 vertices / 960 faces per atom**, i.e. ~9 M vertices
for an 18k-atom model — which is far more tessellation than small on-screen balls
need and inflates both the CPU merge and every GPU frame. It now uses a coarse,
config-tunable sphere (`balls.sphere_lat`/`sphere_lon`, default 10×16 = 160
verts) via `MolView._balls_sphere_segments()`, and the merge uses broadcasting
instead of `np.repeat`. Atom build dropped ~180 ms → ~40 ms and the per-frame
triangle count fell ~3×. `_build_sphere_mesh(radius, lat, lon)` is now
parameterised; the gaussian/selection glyph sites keep the smooth default.

The **metaball/surface** representations were dominated not by marching cubes
(~0.2 s) but by **ambient occlusion** (`geometry/ambient.py`), whose default path
was a numba **O(n²)** double loop over the *mesh vertices* — tens of thousands of
them — costing ~18 s. AO is now an O(n) numba **cell list** (uniform grid, cell =
radius, exact and bit-identical to the O(n²) reference). Metaball dropped ~5.7 s →
~0.8 s. AO is shared by balls/cartoon/surface/metaball, so all benefit.

The **Gaussian surface** (`_build_surface_mesh_scene`) coloured vertices and
computed analytical normals with a per-vertex/per-atom Python double loop
(hundreds of thousands of `math.exp`). It now uses the same vectorised fixed-k
KD-tree approach as the metaball path (query the k=32 nearest atoms once, then
array-wise weights/colours/gradient-normals) — bit-exact for real structures
since the k-nearest set captures every atom within the cutoff. Surface build
~2.1 s → ~0.4 s. Note this is the atom-Gaussian "Surf" path; **accessible-volume
(AV) overlays render separately** — `add_point_overlay` (transparent point cloud,
`av_viewer_3d`) or `add_surface_overlay` → `_generate_surface_mesh_from_points`
(voxel + `scipy.ndimage` + marching cubes, ~9 ms for 60k points, already fast).
The real AV-workflow cost was that every AV show/update calls `_update_view`,
which rebuilds the **whole structure scene** (cartoon/atoms/surface) — so the
builder speedups above dominate AV-interaction latency, not the AV mesh itself.

**AVs render as a transparent surface envelope, never a transparent point cloud.**
A dense AV drawn as tens of thousands of transparent sphere sprites is
fragment-overdraw bound — each sprite runs the full lighting fragment shader and
they stack many-deep under alpha blending, so rotation crawls. `AVViewer3D.show_av`
therefore calls `add_surface_overlay` (→ `_generate_surface_mesh_from_points`:
voxelise → dilate → smooth → marching cubes), producing one **transparent closed
mesh** — a ~60k-point cloud becomes ~3.6k verts / ~7.2k triangles with minimal
overdraw, the same volumetric read for a fraction of the GPU cost. The overlay
falls back to points only if meshing fails (too few points). `add_point_overlay`
still exists for genuine point data and now caps/subsamples above
`overlay.max_points` (default 30k) as a defensive guard.

**Dependency policy — only IMP (plus NumPy/numba), no scipy/scikit-image.**
ChiMOL has **zero scipy/scikit-image imports**. All neighbour queries that used
`scipy.spatial.cKDTree` — surface/metaball colouring (Gaussian-weighted colour +
gradient normal), surface-exposed-atom masking, and distance-based selection
(`sele_parser`) — go through a shared numba cell-list in `geometry/neighbors.py`
(`shade_from_atoms`, `count_within_radius`, `within_distance_mask`), each verified
bit-exact against a brute-force reference. Removing scipy here also made the
colouring **faster** (metaball ~0.8 s → ~0.4 s, surface ~0.43 s → ~0.16 s): a
cell-list radius query beats a KD-tree k-nearest for this dense, local pattern.
The SES surface's distance transform is a numba separable exact EDT
(`surface._distance_transform_edt`, Felzenszwalb-Huttenlocher), matching
`scipy.ndimage.distance_transform_edt` exactly. The surface stack was migrated off
the scientific stack: `_generate_surface_mesh_from_points`
(the AV/point surface) uses NumPy `_binary_dilate_6` (6-connected, matches scipy's
default element) and `_gaussian_blur_3d` (separable 1-D convolution, matches
`scipy.ndimage.gaussian_filter` to ~1e-16) instead of `scipy.ndimage`; and all
isosurface extraction (AV, metaball, gaussian/EDT surface) uses a self-contained
numba marching cubes (`geometry/marching_cubes.py` + the canonical
`_mc_tri_table.py`) instead of `skimage.measure.marching_cubes`. The numba mesher
welds vertices via a per-grid-edge index, so its output is **bit-identical to
skimage's** (same vertex/triangle count, same bbox, outward normals, matching
winding) — a drop-in; it is ~4–9 ms for an AV-sized grid. IMP's own isosurface
(`IMP.display.IsosurfaceGeometry`, CGAL) was evaluated and rejected: correct but
~1.7 s for a 60³ grid (CGAL does Delaunay refinement, not fast MC) and its
`em.get_grid` rejects negative origins. The `marching_cubes` tables are validated
against the edge table across all 256 cases and on an analytic sphere
(`test_marching_cubes.py`), with no skimage in the tests.

**Spatial-search dependency note:** the AO neighbour count deliberately uses a
numba cell list, not scipy (`scipy` is *not* a declared dependency) and not IMP
(which *is*). IMP was evaluated: `IMP.algebra.NearestNeighbor3D.get_in_ball` is an
**approximate** search — it silently drops interior neighbours even at
`epsilon=0`, so it undercounts — and `IMP.core.GridClosePairsFinder` materialises
every close pair (~10 M on a dense mesh → slower than the O(n²) loop). numba
already accelerates this file, so the cell list stays dependency-clean and exact.

# PyMOL parity (cartoon + navigation)

The cartoon and mouse navigation are modelled on PyMOL (source under
`junk/pymol-open-source`, `layer2/RepCartoon.cpp` + `layer1/SceneMouse.cpp`).

**Cartoon ribbon orientation (`geometry/cartoon.py`).** The per-residue ribbon
"up" is the **peptide-plane normal** `normalize((N−C)×(N−O))` (PyMOL PASS1), not
the raw `C−O` carbonyl direction — the latter is noisy and spins around the helix
axis, which is what made helices render as twisted tape. `_refine_orientations`
then applies PyMOL's three anti-twist passes before spline sampling: **round
helices** (`up = normalize(axis×tangent)` from a running CA-difference axis, so
the oval circles a smooth axis), **flat sheets** (4-cycle 3-point box average of
orientations across a β-strand), and **refine-normals** (force ⊥ tangent + forward
sign propagation). Cross-section dims already match PyMOL (oval 0.25×1.35, rect
0.4×1.4, loop r=0.2). Do not revert the orientation to `C−O`.

**Navigation (`renderer/qtgl.py`).** The camera orientation is a **3×3
world→camera rotation matrix** (a virtual trackball), not a turntable. Left-drag
= trackball (sphere radius `0.45·min(W,H)`, axis `cross(n_prev,n_cur)`,
`mouse_scale`=1.3, roll-damped `1/(1+|axis.z|)`, left-multiplied + SVD
re-orthonormalised); middle-drag = pan; right-drag = dolly (right-click still
opens the menu). Camera right/up/forward are the rotation rows; the 18-float view
state stores the matrix in slots 0–8 (legacy elevation/azimuth in 10–11 still
decode), and `raytracer._camera_from_view_state` reads the same so the GL view and
the offscreen raytrace stay consistent. `reset_view(distance,elevation,azimuth)`
keeps its signature (builds the matrix internally).

# Structure loading (fallback contract)

`io/structure.py:load_structure_payload` tries the core `Structure` reader first
and, when that is unavailable or fails, parses the file itself via
`_parse_pdb_backbone` into a `PdbBackbone` (all `ATOM`/`HETATM` coordinates plus
the CA trace with its residue numbers, names and chain ids).

**The residue metadata is load-bearing for rendering, not just for the info
panel.** `_update_trace` and the cartoon builder derive segment boundaries from
residue/chain ids; when those are `None` they fall back to a single span and
spline **one continuous polyline through every point in file order**, waters
included — the "spaghetti" failure mode. hGBP1 (1dg3) is the reference case: with
metadata it renders as **5 segments**, suppressing 4 spurious CA–CA connections,
the longest spanning 22.2 Å against a real bond of ~3.8 Å.

Four constraints follow, all load-bearing:

1. **Never bundle the `Structure` import with GUI imports.** It is pure core
   code; sharing a `try/except` with anything that pulls in Qt means a GUI-side
   import failure silently disables the reader for *every* file.
2. **Never swallow a reader failure silently.** Falling back is legitimate;
   falling back without a log line makes the degradation undiagnosable, since the
   symptom (a bad-looking render) does not name its cause.
3. **Keep the fallback non-lossy.** Anything that reaches `add_coordinates` for a
   PDB should carry `trace_coords`/`res_ids`/`res_names`/`chain_ids`, so a reader
   failure costs accuracy, not a broken picture.
4. **Build the CA trace from `ATOM` records of the first model only**, skipping
   non-first altlocs. Including `HETATM` puts ligands and waters on the backbone;
   including further `MODEL`s makes the trace jump between conformers.

Because the fallback carries a *separate* CA trace, `set_coordinates` keeps two
coordinate stores: `_coords` (the trace, driving cartoon/trace) and
`_all_atom_coords` (every atom, driving atoms/sticks/surface). Two rendering
paths key off `_all_atom_coords` and must not assume the structured `_atoms`
array exists:

- **Atoms.** The per-residue ball path in `_update_atoms` requires `_atoms`; the
  raw-coordinate branch renders every atom straight from `_all_atom_coords`
  (mirroring `get_atom_sphere_data`). Without it the code falls through to a
  ~50-point sparse CA sampling of `_coords` — "not all atoms show".
- **Sticks.** `set_coordinates` computes `_bond_pairs` from the **raw** (unscaled)
  coordinates, exactly as `set_structure` does. Skipping this leaves
  `_bond_pairs is None` and `_update_sticks` renders nothing.

The raytracer path (`get_atom_sphere_data`) already read `_all_atom_coords`
directly, so an offscreen raytrace does **not** catch either gap — regressions
here must be verified through the interactive `_update_atoms`/`_update_sticks`
scene builders (see `test_chimol_fallback_render.py`).

**Every per-atom colouring path must guard on `_all_atom_res_ids is not None`,
not on `_residue_ids`.** Since the fallback populates `_residue_ids` (per-CA) but
leaves `_all_atom_res_ids` as `None`, any renderer that gates its atom→residue
colour mapping on `_residue_ids` and then does `np.asarray(self._all_atom_res_ids)`
will iterate a 0-d `asarray(None)` and raise. `_update_metaballs`, `_update_surface`
and the sticks path already guard correctly; `_update_dots` did not, and because it
runs inside the shared scene builder its `TypeError` aborted the **whole** build —
so dots *and* metaballs (and everything else) vanished at once. A full-scene build
with the representation enabled, not just the isolated `_update_*` call, is the test
that catches this class of regression.

**The fallback must seed a scaled `_all_atom_radii`, because the surface and
metaball density renderers derive their Gaussian sigmas from it in the *scaled*
coordinate frame.** `_all_atom_coords` is scaled by `_scale_factor` (default 10),
and `set_structure` scales the real `radius` field to match. A raw-coordinate
object has no radii, so `_update_metaballs`/`_update_surface` fall back to a
constant sigma (~1.5–1.8) that is sized for *unscaled* Ångström and therefore
~`_scale_factor`× too small: the density barely overlaps between atoms and
marching cubes returns a few disconnected specks (148l metaballs: **888 vertices**)
instead of a molecular envelope (**131k**). `set_coordinates` now seeds
`_all_atom_radii = _DEFAULT_ATOM_RADIUS_A (1.5 Å) × scale`, just below the real vdW
radii the reader assigns (1.5–2.0 Å), so balls, surface and metaballs all render in
the right units and match the structured path. Guard a mesh-density regression by
asserting the metaball vertex count and that its bounding box spans the atom cloud,
not just that a mesh exists.

# Display config (`chimol_display.json`) — two defaults, and a legacy shadow

Visual tunables live in `chimol_display.json`, loaded by `config.py:load_display_config`
into the module-global `_DISPLAY_CONFIG`. **There are two copies of every default and
they drift:** the shipped package `chimol_display.json` *and* a hardcoded `default = {…}`
dict inside `load_display_config`. The dict is not just a fallback for a missing file —
it is shallow-merged over whatever file loads, filling any **section the file omits**. So
editing only the JSON is not enough; a value the loaded file lacks comes from the dict.
**Change both, together.**

Worse, the loader prefers, in order: the user copy `~/.chisurf/chimol_display.json`, then
legacy `molview_display.json` / `protview_display.json` in the same settings dir, and only
then the package file. A stale legacy `protview_display.json` (as on the author's machine)
therefore **shadows the shipped package config entirely** and never expires — its sections
freeze at old values, and any section it omits (e.g. `metaball`) falls through to the code
`default` dict, *not* the package JSON. Net effect: package-JSON edits can be invisible to
a real user. When tuning a representation's look, verify through `load_display_config()`
(what the GUI actually reads), not by reading the package JSON. The load path is a footgun
worth simplifying — a stale legacy file should not outrank the shipped config.

Metaball look is tuned for a soft, clay-like surface: `iso_value` 0.1 + `sigma_factor` 2.2
(a config knob replacing a hardcoded ×1.5 sigma multiplier) fuse atoms into rounder blobs;
`alpha` 1.0 (opaque) lets the baked AO read; `ao_strength` 0.9 / `ao_radius` 7.0 deepen
crevice shadows; `specular_strength` 0.12 / `shininess` 22 kill the wet-plastic gloss. The
gloss in the GL shader (`qtgl.py` fragment) comes mostly from a fake-MatCap env reflection +
sun highlight gated by `specStrength`, so a matte look is driven by dropping specular, not
shininess alone.

# Documentation Work

- No `README.md` under `chisurf/plugins/chimol/` yet — add one covering the
  viewer, the `cmd` surface, and `chimol-cli`.
- Manifest `categories` drift is a known cleanup item (see
  [assessment INC-07](/specs/assessment.md)).
- Document which `cmd` tiers are implemented vs. stubbed so scripts fail
  predictably.
