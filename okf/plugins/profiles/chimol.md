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
and falls back to `_simple_load_pdb_coords` — a bare `ATOM`/`HETATM` coordinate
array. The fallback is **lossy in a way that is visible on screen**: it carries no
residue ids, residue names or chain ids, so

- the info panel reports `Residues: ?` and `Radius of gyration: ?`,
- the Sequence panel reports `(no sequence information)`, and
- `_update_trace` cannot find segment boundaries and splines **one continuous
  polyline through every atom in file order**, waters included — the "spaghetti"
  failure mode.

Two constraints follow, and both are load-bearing:

1. **Never bundle the `Structure` import with GUI imports.** It is pure core
   code; sharing a `try/except` with anything that pulls in Qt means a GUI-side
   import failure silently disables the reader for *every* file.
2. **Never swallow a reader failure silently.** Falling back is legitimate;
   falling back without a log line makes the degradation undiagnosable, since the
   symptom (a bad-looking render) does not name its cause.

# Documentation Work

- No `README.md` under `chisurf/plugins/chimol/` yet — add one covering the
  viewer, the `cmd` surface, and `chimol-cli`.
- Manifest `categories` drift is a known cleanup item (see
  [assessment INC-07](/specs/assessment.md)).
- Document which `cmd` tiers are implemented vs. stubbed so scripts fail
  predictably.
