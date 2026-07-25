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
PyMOL `cmd` API. It is a **declarative, signature-driven command language**
modelled on PyMOL's four-piece design (registry → driver → tokenizer → binder),
adapted to Python introspection:

- **`registry.py`** — a `@command(name, *, aliases=(), mode=...)` decorator tags
  a real-signature method; `collect_commands(instance)` walks the MRO and builds a
  `{name → CommandSpec}` registry plus a `Shortcut` minimal-unique-prefix index
  (so `zo`→`zoom`).
- **`argparse2.py`** — the generic `tokenize(arg_str, mode)` (comma/keyword/
  bracket/quote-aware, with `raw1`/`raw2` verbatim-tail modes for
  `alter`/`iterate`) and `bind_and_call(func, pairs)` which maps positionals/
  keywords to the method's `inspect.signature` and coerces each string per the
  parameter annotation (`int`/`float`/`bool`/`str`/`Selection`, PEP-563 aware).
- **`base.py:do()`** — the single driver: `@script` execution, then resolve the
  head token in the registry and tokenize+bind+call. There is **one** dispatch
  path; the legacy `_cmd_x(args: List[str])` + `_mixin_commands()` pattern and its
  adapter have been fully removed.

Adding a command is therefore writing one annotated method
(`def zoom(self, sel: str = "all", buffer: float = 2.0)`); parsing, keyword args
(`zoom polymer, buffer=5`), coercion, and the callable Python API all come for
free. Commands are grouped by concern across `command` (aggregator),
`base`, `loader`, `rendering`, `selection`, `sele_parser`, `measurements`,
`editing`, `exporting`, `animation`, `lifecycle`. The former `core.py` monolith
and the never-registered `rmf.py` mixin were deleted.

Implemented tiers:

- **Shell & IO** — `@script` execution, `help`/`load`/`open`/`fetch`/`fetch_emdb`/
  `fetch_ihm`, `objects`/`get_names`, `quit`/`exit`, error routing.
- **Camera verbs** — distinct `center` / `orient` / `zoom` / `reset` semantics.
- **Color** — modes plus `byelement`, `bychain`, `spectrum`, and named colors;
  per-selection RGBA overrides.
- **Selection grammar** — `sele_parser.py` is a recursive-descent
  tokenizer + AST parser + evaluator supporting `all`/`none`/`resi`/`resn`/
  `name`/`chain`/`elem`/`and`/`or`/`not`/`within`/`around`/`byres`/`expand` and
  `/object/chain/resi/name` macro syntax. **The combined `TOKEN_REGEX` must not
  carry inline `(?i)` flags** — once joined with `|` they land mid-expression and
  Python 3.11+ refuses to compile the pattern, which silently broke every
  selection evaluation (color/select/alter/remove/align on real structures);
  case-insensitivity lives in a single `re.IGNORECASE` on `re.compile`.
- **Per-atom representations** — `ball_mask` / `sticks_mask` are per-atom masks,
  so `show sticks, name CA` and `hide spheres, resi 1-20` work at atom
  granularity.
- **Measurement & analysis** — `distance` / `angle` / `dihedral` create persistent
  3D overlays (dashed lines + floating value labels) via a `SceneObject`
  `kind="text"` geometry; `rms`/`rms_cur` and `align`/`super` (iterative
  outlier-rejection Kabsch, with typed `cutoff`/`cycles` keyword args) are present.
  Every one of them fits the *renderer's* coordinates, which are Angstrom times
  `_scale_factor`, so each converts at that boundary: `align`/`super` divide both
  coordinate sets by the scale up front — the rejection `cutoff` and the reported
  RMSD are then the Angstrom the user typed and expects — and scale the fitted
  translation back for `apply_transform_to_object`, which takes scene units.
- **Object lifecycle** — `delete`/`reinitialize`/`copy`/`split_chains`, plus
  `set_name` (rename) and `count_atoms` (selection → atom count).
- **Settings** — `set`/`get`/`unset`/`toggle`/`help_setting` over the registry in
  `chimol/settings.py` (see below).
- **Secondary structure** — `dss` recomputes H/E/C from the backbone, discarding
  the deposited `HELIX`/`SHEET` annotation a PDB load adopts by default.

Known remaining gaps (higher PyMOL tiers): chemistry-light editing
(`bond`/`h_add`), volume/map objects, and the movie keyframe system
(`mdo`/`mview` are stubbed). Keep unimplemented command names registered so the
CLI emits a friendly "not yet implemented" message.

## Settings (`chimol/settings.py`)

PyMOL exposes one flat namespace (`cartoon_loop_radius`, `ray_shadow`,
`field_of_view`); chimol stores its tunables nested by subsystem in
`_DISPLAY_CONFIG`. `settings.py` is the single table mapping one onto the other,
and `set`/`get`/`unset`/`toggle` resolve through it — exact name, unambiguous
prefix (`cartoon_oval_w`), or a dotted config path (`metaball.alpha`) for entries
with no PyMOL equivalent.

Two invariants make the table trustworthy, both pinned by tests:

1. **Every entry is live** — a setting is registered only if some code reads the
   path it names, so an unknown or dead name is *reported* rather than silently
   accepted. The config previously carried a second, flat copy of ~36 PyMOL names
   that nothing read; it is gone, and a test keeps it from returning.
2. **The config is the storage** — nothing is cached in the settings layer, so an
   open viewer sees a change on its next redraw.

# The GUI follows PyMOL's layout

A PyMOL user should be able to drive chimol without being taught. Two surfaces
carry that, both transcribed from PyMOL's **source** rather than from
screenshots — `pymol/menu.py` and `pymol/_gui.py` define their menus
declaratively, so the copy is mechanical and testable.

**Per-object A/S/H/L/C menus** (`app/object_menus.py`, `app/objects_panel.py`).
Entry for entry from `mol_action`/`mol_show`/`mol_hide`/`mol_labels`/`mol_color`:
same entries, same order, same separators, same labels, including PyMOL's stray
trailing space in `"by ss  "`. **The buttons live on each molecule's row**, next
to its visibility box, name and `current/total` state counter, with a permanent
grey `all` row above acting on everything. That is not cosmetic — a single shared
button row retargets every action at whatever is selected, which no PyMOL user
expects. Implemented as a Qt item widget per list row, so the item keeps its
check state and the existing handlers still fire; Qt's own check indicator is
hidden and the item text blanked, or both render underneath the row widget.

**Main menu bar** (`app/menu_bar.py`), in PyMOL's order and wording.

The two surfaces make **opposite calls about gaps**, deliberately:

- Within a menu, an entry chimol cannot do stays **visible, disabled, and
  explained in its tooltip**. Dropping it would change the menu's shape and hide
  the gap; wiring it to something approximate would misreport what happened.
- A whole top-level menu chimol cannot fill at all (Build, Movie, Scene, Wizard,
  Plugin) is **omitted**, with the reason recorded in `OMITTED_MENUS`. A menu has
  no shape to preserve, and an empty one is a promise with nothing behind it.

Every entry runs through the same command layer the command line uses and is
echoed there, so clicking teaches the command. Tests pin the labels and order
against PyMOL's own tables (re-read from a live PyMOL when it is importable),
that every wired verb is a registered command, that every `set <name>` resolves
to a real setting, and that no disabled entry lacks a reason.

# Cartoon geometry: PyMOL's pipeline, and where chimol diverges

With PyMOL's source available, the cartoon pipeline can be compared step for step
rather than by matching rendered meshes. `RepCartoonGeneratePoints`
(`layer2/RepCartoon.cpp:~4255`) runs, in order:

1. `RepCartoonRefineNormals` — `cartoon_refine` (default **5**)
2. `RepCartoonFlattenSheets` — `cartoon_flat_sheets` (**on**),
   `cartoon_flat_cycles` (**4**)
3. `RepCartoonSmoothLoops` — `cartoon_smooth_loops` (**off** by default)
4. recompute differences and normals from the smoothed positions
5. recompute tangents into `tv`
6. `RepCartoonFlattenSheetsRefineTips` — `cartoon_refine_tips` (default **10**)

**Ported faithfully: flat sheets.** Per strand run, `cartoon_flat_cycles` passes
of a *uniform* three-point average — PyMOL's `scale3f(t0, 1/(f*2+1))` with
`f = 1`, not a weighted kernel — applied to the positions **and** the orientation
vectors, followed by re-orthogonalising each orientation against
`normalize(p[b+1] - p[b-1])`. Smoothing the path while leaving the up-vectors
pleated keeps half the twist, which is what an earlier weighted-kernel version
here did. A run's own end points are anchors (`first+f .. last-f`).

**The per-residue stage is `geometry/guide_frames.py`.** chimol used to derive
tangents from the *sampled spline*, which works but leaves nowhere to put the two
conditioning steps PyMOL runs before any sampling — so they could not be patched
in, and the stage had to exist. It transcribes four functions:

| PyMOL | here |
| --- | --- |
| `RepCartoonComputeDifferencesAndNormals` | `differences_and_normals` |
| `RepCartoonComputeTangents` | `tangents_from_normals` |
| `RepCartoonRefineNormals` | `refine_normals` |
| `RepCartoonFlattenSheetsRefineTips` | `refine_sheet_tips` |

Two distinctions are easy to lose and load-bearing:

1. **`nv` is not `tv`.** `nv[a]` is the unit direction from residue `a` to `a+1`
   (a segment direction, `n−1` of them); `tv[a]` is the tangent *at* residue `a`,
   the normalised **head-to-tail sum** of the two directions meeting there.
2. **`refine_tips` acts on the tangents.** The `/* normal */` comment in the C++
   is stale — `tv` is written by `RepCartoonComputeTangents`. With the default
   weight of **10** the neighbour dominates, which is the point: a strand tip
   otherwise takes its direction from the loop it joins and the arrowhead points
   off the strand axis. Measured on a strand running +x into a loop peeling into
   +y, the tip tangent's stray component drops from 0.36 to 0.03.

`refine_normals` (on for single-state objects) runs four passes: orthogonalise
against the tangent; offer the vector and its inverse as candidates, **except in
a helix**, where inverting would confuse inside and outside; sweep forward taking
whichever candidate agrees with the neighbour already decided, which is what
stops the ribbon flipping face; then soften kinks where a residue disagrees with
*both* neighbours (`dot(v,v₊)·dot(v,v₋) < −0.1`).

`cartoon_smooth_loops` (`RepCartoonSmoothLoops`) is implemented too, so the
setting is not a lie, and **off by default as in PyMOL** — rounding the coil
pulls it away from the real backbone. It differs from the sheet pass in two ways:
the run is widened by one residue into the flanking element, so the smoothing
does not stop dead at the junction and crease there; and the orientations are
renormalised but *not* re-orthogonalised, since a loop has no face to keep flat.

**Every PyMOL setting the pipeline reads is now registered** — `cartoon_throw`,
`cartoon_power`, `cartoon_power_b`, `cartoon_refine_tips`,
`cartoon_refine_normals`, `cartoon_smooth_loops`, `cartoon_smooth_cycles` — so
they are reachable as `set cartoon_throw, 2.0` and not only by dotted path.

Measured on 148L, mean distance from the strand ribbon to its strand CAs:
PyMOL **1.56 Å**, chimol **1.66 Å** — not exactly comparable, since PyMOL's `dss`
calls 12 residues strand there where the deposited records (which chimol honours)
call 14.

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

The cartoon and mouse navigation are modelled on PyMOL. **The reference is a
real PyMOL install, not the C++ source** — `pymol -qc` can export its own cartoon
as OBJ, and under an identity view the vertices come out in PDB Ångström, so
chimol's mesh can be compared to PyMOL's numerically and rendered back through
chimol's *own* raytracer with the same camera. Any behaviour claim below was
measured that way on **148L**; re-measure rather than reason about it. The
working parity number is the **symmetric mean surface distance** between the two
cartoon meshes plus per-SS cross-section dimensions. Give both programs the
**same** secondary structure before reading the number, otherwise an assignment
difference is mistaken for a geometry one: on the full RCSB 148L (whose
`HELIX`/`SHEET` records both honour) the distance is **0.428 Å** and helix,
strand and loop cross-sections all agree to ~0.1 Å.

## The extrusion frame convention is load-bearing

`_extrude_shape` maps a cross-section's **y component onto `side`** and its
**z component onto `up`** (the residue orientation vector). PyMOL's
`cartoon_oval_width` / `cartoon_rect_width` are the *thickness* along that
normal and `…_length` the *breadth* across the ribbon, so the broad extent
belongs on **y**. Swapping the two rotates every ribbon 90° about its own path —
helices become edge-on twisted tape and strands stand on their side. This was
the single largest visual defect. Cross-section dims match PyMOL
(oval 0.25×1.35, rect 0.4×1.4, loop r=0.2).

## Cartoon ribbon orientation (`geometry/cartoon.py`)

The per-residue ribbon "up" starts as the **peptide-plane normal**
`normalize((N−C)×(N−O))` (PyMOL PASS1), not the raw `C−O` carbonyl direction —
the latter is noisy and spins around the helix axis. Do not revert it.
`_refine_orientations` then applies PyMOL's passes:

- **Round helices** — `_helix_radials` sets the normal to the outward radial of
  the local helix cylinder, taken from the **exact bisector**
  `−normalize(normalize(ca[i−1]−ca[i]) + normalize(ca[i+1]−ca[i]))`. Do not go
  back to a chord such as `ca[i+2]−ca[i−2]`: at ~100°/residue that chord still
  carries a large radial component, and clamping it at run ends put the last turn
  of every helix 40–60° out. Run ends have no all-helix neighbourhood, so their
  radial is **extrapolated** by rotating a neighbour's about the run's own axis
  by its measured twist — copying it verbatim leaves the end ring a full
  turn-step out of phase.
- **Flat sheets** — a 4-cycle 3-point box average of orientations across a strand.
- **Refine normals** — force ⊥ tangent, then propagate the sign. **The sign
  propagation must skip helices.** Inside an α helix the normal is radial and
  turns ~100°/residue, so consecutive normals have dot ≈ cos(100°) = −0.17; a
  plain `dot < 0 → negate` rule flips *every* residue, and the resulting
  alternating field partly cancels when interpolated. Only near-antiparallel
  pairs are genuine flips.

Orientations are densified with `_sample_orientations` (**slerp**), never with a
Catmull-Rom spline: a cubic fitted through four unit vectors ~100° apart
overshoots the arc and can nearly cancel.

## The path needs two SS-specific corrections, not just the spline

A spline through the CA trace is not what PyMOL draws, and both defaults matter:

- **`cartoon_round_helices`** (PyMOL default on) — measured, PyMOL's ribbon
  centerline sits at radius **2.17 Å** midway between residues whose CAs are at
  2.23 Å, dropping to 1.88 Å with the setting off. A Catmull-Rom through
  100°-spaced points sags to ~0.83 R, so chimol pinched at every turn.
  `_round_helix_path` replaces those samples with the true helical arc —
  interpolating the axis point and cylinder radius linearly and slerping the
  radial — which still passes exactly through every CA, so the joins to the
  flanking loops stay continuous.
- **`cartoon_flat_sheets`** (PyMOL default on) — it does **not** only affect
  orientation. Measured, PyMOL's strand ribbon runs **1.3 Å off** the CAs with
  the setting on and 0.4 Å off with it off: it de-pleats the backbone.
  `_flatten_sheet_path` applies the same 4-cycle `(p[i−1] + 2p[i] + p[i+1]) / 4`
  over strand residues, leaving residues outside the strand fixed so the loop
  joins do not move. Without it a strand's ±1.9 Å pleat forces the plate to
  writhe along its length.

## Strand arrowheads

Measured from PyMOL's mesh, a strand's half-breadth goes body ~1.0 Å → arrow
base ~2.2 Å → tip ~0.3 Å: it flares to about twice the body and comes to a
point, with the thickness unchanged. `_extrude_shape` therefore accepts an
anisotropic `(M, 2)` `vert_scale` for the `side` and `up` axes (normals are
transformed by the reciprocal, the inverse transpose). `arrow_sampling` is in
**residues** and must be multiplied by the subdivision count before being cut off
the sampled path — treating it as a sample count makes the arrow a fraction of
one residue long and invisible.

## `_sample_path` emits every knot

Each segment covers `t ∈ [0, 1)` and so never emits its own end point. Skipping
`j == 0` for segments after the first (as it once did, ostensibly to drop a
duplicate knot) therefore deletes **every interior control point**: the cartoon
drifted ~0.3 Å off the CA trace, against PyMOL's ~0.1 Å. Keeping the knots also
makes the residue→sample mapping exact (`residue i → sample i * subdivisions`),
which the SS block boundaries and the round-helix pass depend on. The
vectorisation parity test in `test_geometry_vectorized.py` had frozen the bug
into its reference loop — when changing sampler behaviour, check that the
reference is not simply enshrining the old bug.

## Secondary structure: prefer the author's records, then tidy

**The deposited `HELIX`/`SHEET` records win when the file has them.**
`io/structure.parse_pdb_secondary_structure` reads them and
`MolView._apply_deposited_secondary_structure` overrides the computed codes,
which is also what PyMOL does — it only recomputes when asked with `dss`, or
when the file carries no records. On the full RCSB 148L this reproduces the
depositor's annotation exactly (10 helix runs, 3 strand runs, zero mismatches).
`HELIX` and `SHEET` put the chain and sequence number in **different columns**,
so never re-type a fixture record by hand; copy it verbatim.

**Do not tune the computed fallback towards PyMOL's `dss`.** The in-tree test
file `148l.pdb` is header-stripped, so PyMOL runs `dss` on it and reports
strands at 18-20 / 23-27 / 31-34 and helices 3-7 … 146-155. The depositors say
**14-19 / 25-28 / 31-34** and 3-11 … 143-155 — and that is what chimol's own
hydrogen-bond assignment produces. On this structure chimol is closer to the
truth than `dss` is; measuring against `dss` output would be chasing the wrong
target.

The raw H-bond assignment does still need tidying for *drawing*: it left 148L
with **seven** strand fragments, three of them single residues, which the
cartoon renders as detached slivers with no room for an arrowhead.
`tidy_ss_runs` bridges short gaps and drops sub-minimum runs, with **per-type
gap limits** — strands lose bridges readily and are worth closing, but a
one-residue break between two helices is a real kink, so helices are never
bridged.

## The view tuple is PyMOL's, and its transpose is a mirror

`renderer/view_state.py` is the single Qt-free owner of the 18-float camera
tuple, shared by the GL widget, the raytracer and `get_view`/`set_view`. It emits
**PyMOL's exact layout** so views can be copied between the two programs.

**PyMOL keeps the camera basis in the matrix _columns_.** chimol works internally
with a world→camera rotation whose *rows* are the camera axes, i.e. the
transpose. Reading PyMOL's nine floats straight into a row-major 3×3 and using
its rows gives the inverse rotation, which renders the molecule **mirrored** —
this silently produced left-right flipped output. Verify with an asymmetric
marker scene (+X red, +Y green, +Z blue) under a lopsided rotation, not with an
identity view, which cannot tell the two readings apart. The rest of the layout
matters too: slots 9-11 are the camera position in camera space `(0, 0, −distance)`
(chimol's older tuples put a positive distance in slot 9, which is what makes the
two unambiguous on input), and slot 17 is the field of view.

**The sign of slot 17 reads backwards from the obvious guess.** PyMOL writes a
**negative** field of view for its default *perspective* camera and a positive
one when `orthoscopic` is on — measured from `cmd.get_view()` with the setting
toggled both ways, and pinned by a test carrying a real PyMOL tuple. The older
chimol layouts predate the flag and always wrote a positive value, so the sign
is only honoured in the PyMOL branch. `ray` honours the field of view rather than
assuming a fixed lens.

**Framing follows the field of view.** `view_state.distance_for_radius` is
PyMOL's rule, `d = radius / tan(fov / 2)` — verified against `cmd.zoom` for radii
5/10/20 Å at 20° and 45°, agreeing to 5 significant figures. `fit_to_radius` uses
it, so widening the lens pulls the camera in instead of shrinking the molecule.

**What gets fitted is `view_state.framing_radius`.** PyMOL's default
(`complete=0`) fits the largest half-extent of the axis-aligned bounding box;
`complete=1` fits the bounding sphere so nothing can be clipped. Both are
measured on the **world** axes, not the camera's — which looks like an oversight
and is not: it makes the zoom level independent of orientation, so turning the
molecule does not make it breathe. Confirmed by zooming a 30×5 Å bar at
0/30/45/90° of roll, where PyMOL returns the same distance every time (the
camera-space extent would fall to 21 Å at 45°). `zoom` fits **every atom**, not
the CA trace: the side chains reaching furthest out are exactly the ones a trace
omits. Residual gap: PyMOL measures the extent of the *rendered representation*,
so its camera sits ~3 % further back on 148L (24.47 Å vs 23.77 Å); that padding
is representation-dependent and is not modelled.
The default field of view is **20°**, PyMOL's, which is what makes a `set_view`
tuple copied from PyMOL frame the molecule the same way here; it was previously a
hardcoded 45° with a `distance = 3 × radius` framing rule that matched no lens in
particular.

**Navigation (`renderer/qtgl.py`).** The camera orientation is a **3×3
world→camera rotation matrix** (a virtual trackball), not a turntable. Left-drag
= trackball (sphere radius `0.45·min(W,H)`, axis `cross(n_prev,n_cur)`,
`mouse_scale`=1.3, roll-damped `1/(1+|axis.z|)`, left-multiplied + SVD
re-orthonormalised); middle-drag = pan; right-drag = dolly (right-click still
opens the menu). Camera right/up/forward are the rotation rows; serialisation
goes through `view_state.pack_view_state` / `unpack_view_state` (above), which
both `get_view_state` and `raytracer._camera_from_view_state` call, so the GL
view and the offscreen raytrace cannot drift apart.
`reset_view(distance,elevation,azimuth)` keeps its signature (builds the matrix
internally).

# Ambient occlusion (the one place chimol is ahead)

PyMOL has no ambient occlusion at all, so this is where chimol can look better
rather than merely the same. `geometry/ambient.py` holds two estimators and they
answer different questions:

- `_estimate_ambient_occlusion` counts neighbours inside a radius. Cheap and
  **normal-agnostic**, so it measures *crowding*, not *concavity* — a bulge in
  the middle of a crowd came out as dark as the pit beside it.
- `occlusion_from_spheres` is real AO. For each vertex it accumulates the
  fraction of its **hemisphere** blocked by nearby spheres,
  `1 − cos α` with `sin α = r / d`, weighted by `cos θ` against the vertex
  normal, and combines contributions as `1 − exp(−strength · Σ)` so a dense
  neighbourhood deepens without ever saturating to black. Numba cell list over
  the occluders, with a chunked NumPy fallback that agrees to 1e-12.

**Baked into vertex colours at build time, not computed per frame.** The
occlusion of a rigid molecule does not depend on the camera, so this costs
nothing while the view moves and cannot shimmer the way a screen-space estimate
does — and it needs no `ray`, no FBO and no second shader pass. Rebuild cost on
1DG3 (540 residues, ~67 k cartoon vertices): 0.139 s → 0.25 s.

**Occlude with the right thing.** A cartoon ribbon threads straight through its
own side chains, so shading it against every atom buries the molecule in shadow —
it is surrounded by geometry that is not drawn. `occlusion.occluders` therefore
defaults to `"residues"` (the backbone trace with a residue-sized radius), which
darkens the grooves between helices as it should. Space-filling spheres pass
`occluders="atoms"` explicitly, because there the atoms *are* the picture.

**The backend gets the occlusion, not only the darkened colour.** The shader adds
ambient, rim, a fresnel-blended environment reflection and a sun highlight, none
of which come from the surface colour — so darkening the pigment alone leaves
them lighting a crevice from directions it cannot see, and the occlusion reads as
an overall dimming rather than as shape. `Geometry.occlusion` carries it to the
backend as a per-vertex GL attribute and the shader damps every non-surface term
by `1 − occlusion`. Two traps here, both load-bearing:

1. **Expand it through the index array.** `_geometry_to_draw_data` flattens an
   indexed mesh into a triangle list; an occlusion array that is not expanded
   with the positions fails the upload's length check and is *silently* dropped.
2. **Verify against the GL widget, not the raytracer.** `QT_QPA_PLATFORM=offscreen`
   cannot create a GL context at all, so a headless check quietly falls back to
   the raytracer and proves nothing about the viewport. Under `cocoa` an
   offscreen surface works (GL 2.1 Metal) and `grab_current_view_image()` returns
   a real frame.

Tunables live under `occlusion.*` in the display config and are reachable via
the settings layer's dotted-path form (`set occlusion.strength, 2.0`): `enabled`,
`strength`, `darkness`, `max_distance`, `occluders`, `residue_radius`. When it is
on, the per-residue neighbour-count shading in `_update_cartoon` is skipped —
running both darkens the cartoon twice.

# Structure loading (fallback contract)

`io/structure.py:load_structure_payload` tries the core `Structure` reader first
and, when that is unavailable or fails, parses the file itself via
`_parse_pdb_backbone` into a `PdbBackbone` (all `ATOM`/`HETATM` coordinates plus
the CA trace with its residue numbers, names and chain ids).

**Ask the core reader for the whole model.** Its defaults are tuned for
modelling: `read_coordinates` selects with `NonWaterPDBSelector` and
`convert_atoms` drops non-standard residues, so waters, ions, ligands and sugars
never arrive. For a viewer that is wrong — a deposited entry appears without
content the file plainly carries and the atom count disagrees with the file
(148L: 63 atoms short; 1DG3: 341). `_read_full_model` therefore calls the factory
with `keep_water=True, only_standard_residues=False`, falling back to the plain
one-argument call on `TypeError` so a factory that predates the arguments still
works. The core **defaults are unchanged**, and a test pins that, because the
modelling code depends on them.

**What no cartoon draws, the atom representation shows.** `_hetero_atom_mask`
marks every atom whose residue never enters the backbone trace and turns the atom
representation on for them, so waters and ligands are visible on load the way
PyMOL's `auto_show_nonbonded` (on by default, with `auto_show_lines`) makes them
visible there. Those atoms are drawn at their element's CPK colour and scaled by
`nonbonded_size` (0.25, PyMOL's value) rather than their van-der-Waals radius —
a shell of full-size water spheres buries the molecule inside it. Defining the
mask by *absence from the trace* rather than by a residue-name table also catches
incomplete polymer residues: 148L's chain E ends on a lone backbone nitrogen
(`ASN E 163`, no CA), which would otherwise be loaded and then drawn by nothing.

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
2. **Never swallow a reader failure silently — and tell the user, not just the
   log.** Falling back is legitimate; falling back quietly is not, because the
   symptom (a bare CA spring with no secondary structure, sequence or radius of
   gyration) does not name its cause and reads as a rendering bug.
   `_report_degraded_load` logs *and* writes to the command panel, naming the
   file, the reader's error, and what the fallback costs. The info overlay's
   `System: coordinates` line is the other tell that this path was taken.
3. **Keep the fallback non-lossy — including the atom array.** Anything that
   reaches `add_coordinates` for a PDB should carry
   `trace_coords`/`res_ids`/`res_names`/`chain_ids` **and `atoms`**, so a reader
   failure costs metadata, not the picture. The atom array is what separates a
   cartoon from a bare spring: `assign_ss_c3_from_atoms` needs N/CA/C/O to
   assign H/E/C, and `_build_trace_ups` needs the backbone carbonyl to know
   which way the ribbon faces. Without it everything is coil and the cartoon
   degenerates to a thin loop tube threading the alpha carbons — which is what a
   user reports as "ugly cartoon", not as "the reader failed". It must stay
   **index-aligned with `coords`**, because per-atom masks and colours are mapped
   between the two by position; alternate locations are therefore dropped at the
   one point where both are appended.
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
