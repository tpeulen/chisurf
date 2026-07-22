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

# Documentation Work

- No `README.md` under `chisurf/plugins/chimol/` yet — add one covering the
  viewer, the `cmd` surface, and `chimol-cli`.
- Manifest `categories` drift is a known cleanup item (see
  [assessment INC-07](/specs/assessment.md)).
- Document which `cmd` tiers are implemented vs. stubbed so scripts fail
  predictably.
