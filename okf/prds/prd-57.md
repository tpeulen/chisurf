---
type: PRD
prd: "57"
title: "PRD-57: ChiMOL Command Parity and Renderer Migration"
description: Grow the ChiMOL molecular viewer's cmd surface toward parity with a reference molecular-graphics command language, and migrate its renderer to an immediate-mode GUI backend while holding a Qt-free controller/scene contract.
status: draft
phase: "feature track"
resource: chisurf/plugins/chimol/
tags: [prd, plugins, structure, viewer]
timestamp: '2026-07-06T00:00:00Z'
---

# Summary
ChiMOL (formerly moview/ProtView) provides an in-tree molecular viewer with a
command line modelled on the de-facto molecular-graphics `cmd` API. This PRD grows
that command surface incrementally toward parity with that reference language, and
sets the long-term direction for the renderer: swap the hand-rolled Qt/GL label and
console machinery for an immediate-mode GUI backend, while keeping the controller
and scene Qt-free so both backends consume one shared contract. Current-state
plugin facts live in the [ChiMOL profile](/plugins/profiles/chimol.md); this
concept is the forward roadmap.

# Status
Draft / in-progress. Tiers 0–3 of the command roadmap have landed (distinct camera
verbs; `byelement`/`bychain`/`spectrum`/named colors; a full recursive-descent
selection grammar in `cmd/sele_parser.py`; per-atom representation masks; persistent
3D measurement overlays). The renderer already separates a Qt-free scene from
swappable backends (`renderer/scene.py`, `base.py`, `qtgl.py`, `raytracer.py`); no
immediate-mode backend exists yet. Tiers 4–5 and the renderer migration phases below
are future work.

# Command parity roadmap (tiers)

- **Tier 0 — baseline (done).** Command shell + `@script` execution, IO
  (`help`/`load`/`open`/`fetch`/`objects`/`get_names`), viewer toggles, color
  pipeline, residue-range selections and geometric measurements. Feature-complete;
  polish/bugfix only.
- **Tier 1 — low-effort polish (done).** Reference-aligned help/usage text; color
  synonyms and named-color table; distinct `center`/`orient`/`zoom`/`reset`
  semantics with a saved view; measurement overlays instead of console-only output.
- **Tier 2 — selections & per-object control (done for the grammar).** A tokenizer/
  parser/evaluator supporting `all`/`none`/`resi`/`resn`/`name`/`chain`/`elem`/
  `and`/`or`/`not`/`within`/`around`/`byres`/`expand` and `/object/chain/resi/name`
  macros; per-selection `show`/`hide`/`color`; named-selection state; broader
  `set`/`get` bridging remains.
- **Tier 3 — representation depth & chemistry-light editing.** Per-atom visual
  overrides as a first-class channel; full representation mapping (lines/sticks/
  spheres/dots/mesh/surface/cartoon/ribbon) with per-object toggles; read-only
  `alter`/`iterate` label workflows; pseudoatoms; object grouping. Partially landed
  (per-atom masks, overlays).
- **Tier 4 — structural editing & new objects (future).** Chemistry edits
  (`bond`/`unbond`/`h_add`/`rebond`) behind a dedicated backend with undo/redo;
  sandboxed `alter`-style expression evaluation. Volume/map objects have grown
  past a tier bullet -- see **Voxel maps as first-class objects** below.
- **Tier 5 — movies, wizards, analysis (long-term).** Timeline/keyframe animation;
  guided-workflow plugin framework; structural analysis (`align`/`super`/`cealign`/
  `rms`/`intra_fit`).

Keep unimplemented command names **registered** so the CLI emits a friendly "not
yet implemented" message instead of `KeyError`. When porting a command, re-read the
reference implementation's block first to understand hidden side effects.

# Voxel maps as first-class objects

ChiMOL must **display volumetric data**, to the standard of the established
molecular-visualisation tool that is the reference for this (isosurface, mesh and
direct volume rendering, with interactive contour levels). This is not a niche
addition for this group: most of what is looked at here is a density of some kind.

The data that has to be viewable:

| Source | What it is | Where it comes from |
| --- | --- | --- |
| **Accessible volumes** | Where a tethered dye can physically be | the labelling/FRET framework (`IMP.bff`) — the single most-used map here |
| **Probability / occupancy densities** | Where an ensemble puts something | modelling output, MCMC and docking runs |
| **Electron density / cryo-EM maps** | Experimental maps around a model | MRC / CCP4 / MAP files |
| **3D microscopy** | An acquired image stack, **including 3D CLSM** | the imaging side of this codebase |

A 3D CLSM stack loaded in chisurf must be viewable in ChiMOL. That is the
integration test for this whole section: the same viewer that shows the structure
shows the image, in the same scene, so a model can be looked at inside its data.

## Current state

**Landed.** `chimol/volume.py` holds `VolumeGrid` — values with `origin`, `step`
and a 3x3 `rotation`, built primarily from an array in memory, with a voxel
budget and automatic striding, a `mean + 1 sigma` default level, a histogram, and
`isosurface()`. `io/mrc.py` now reads into one of those, honouring the
`mapc/mapr/maps` axis permutation and the two origin conventions (it previously
did neither, so a map loaded transposed and at the scene origin); the old
point-cloud entry point is derived from the grid rather than parsing a second
time. Maps are scene objects with per-level colour and `surface`/`mesh` styles,
reachable as `load_map`, `isosurface`, `isomesh`, `volume_level` and `map_info`.

**Still open:** direct volume rendering (`volume` is registered and declines),
the histogram panel with draggable level markers, colour-by-value transfer
functions, `map_new` from atoms, `map_trim`, and construction from a CLSM stack
loaded in chisurf.

## Chimera is the authority here

For voxel maps specifically, Chimera/ChimeraX is the reference for **behaviour**,
not merely for quality — see the carve-out in [the target spec](/specs/chimol.md).
PyMOL's volume support is thin and this is most of what gets looked at here, so
the data model, the defaults, the terminology and the interface follow Chimera's,
while PyMOL's command *names* are kept where it has them.

## How the reference tool does it

Read from its `map` and `map_data` bundles rather than described from memory,
because the design settles several questions that would otherwise be guessed at.

**The grid** (`map_data/griddata.py`, `GridData`) is `size`, `value_type`,
`origin`, `step`, `cell_angles` **and a 3x3 `rotation`** — so a skewed
crystallographic cell and a rotated grid are both representable, not just an
axis-aligned box. Its docstring is explicit that the data "need not come from a
file", and `ArrayGridData` builds one straight from a 3D NumPy array. That is the
seam an AV or a CLSM stack needs, and it is a *parameter* of the model rather
than an afterthought.

**Big maps are strided, not drawn.** `volume.py` carries a `voxel_limit` (default
**16 Mvoxels**) and `ijk_step_for_voxel_limit()` raises the subsample step until
the displayed region fits under it. So the display cost is bounded by a setting
rather than by the file, and a 4 GB map opens. Region plus step, not "load it
all", is the reason the interface stays usable.

**Three display styles**, one switch: `surface`, `mesh`, `image` — where `image`
is direct volume rendering. `image3d.py` uses a **3D texture** where the driver
allows it (it checks `max_3d_texture_size` and warns, falling back to stacks of
axis-aligned planes), and can keep the colormap on the GPU.

**The interface is a histogram** (`volume_viewer.py`, `Histogram_Pane`). The
data's value distribution is drawn, and contour levels are **markers dragged
along it** — click the histogram to add a level, click a marker to delete it, with
a `Level` box for typing an exact value and a colour per marker. Surface and
image styles keep *separate* marker sets. This is the part worth copying most
directly: it makes choosing a threshold an act of looking at the data rather than
typing numbers and re-rendering, which is exactly the difficulty with an AV or a
photon-count stack whose scale nobody knows in advance.

Alongside it: a data list, a coordinates panel (origin, step, cell angles) and a
precomputed-subsamples panel.

## What has to exist

1. **A map object** on the grid model above — origin, step, cell angles and a
   full 3x3 rotation. A confocal stack's z step is rarely its xy step, and
   treating a grid as cubic silently squashes the picture. It is a real scene
   object with its own name, visibility and colour, regardless of whether it was
   read from a file, computed from atoms, or handed over in memory.
2. **Constructible from an array in memory**, as `ArrayGridData` is. AVs and CLSM
   stacks are already arrays in this process; a round trip through a file on disk
   to see them would be the wrong seam.
3. **A voxel budget with automatic striding.** The single most important thing for
   keeping the viewer responsive, and cheap to implement.
4. **The three styles**: isosurface, mesh, and direct volume rendering. Several
   levels shown at once, coloured separately — this is how an AV is read, a dense
   core inside a diffuse shell. Volume rendering is the mode with no PyMOL
   equivalent worth using and the one that suits microscopy and diffuse
   probability densities, where no single threshold is meaningful.
5. **A histogram panel with draggable level markers**, per the interface above.
6. **Colour by value** through a transfer function or ramp, not one flat colour.
7. **Commands.** `map_new`, `isomesh`, `isosurface`, `volume`, `map_trim` — PyMOL
   names and semantics per the compatibility contract, ChiMOL's additions after
   them rather than in place of them.
8. **A starting level the eye can find**, derived from the data (a quantile of
   occupied voxels) rather than a fixed number, since an AV, a cryo-EM map and a
   photon-count stack do not share a scale.

## Constraints

Volume rendering must not become the thing that makes the viewer slow — see the
trajectory standard in [the target spec](/specs/chimol.md). A map is large and
mostly static, so it uploads once and is not rebuilt per frame; changing a contour
level re-meshes only the map, never the molecule beside it.

No new dependency for reading MRC/CCP4 or for marching cubes: both are already
here, and the format is documented and short. A 3D texture needs no library either
— but it does need the GL path to cope with a driver that will not give it one,
which the reference implementation handles by falling back to plane stacks.

# Renderer migration (immediate-mode GUI backend)

Long-term goal: an immediate-mode GUI backend implementing the `Renderer` ABC, which
removes the fragile `QPainter.begin(self)`-inside-`paintGL` pattern, enables headless
rendering/testing without a `QApplication`, and replaces the hand-rolled label
system and `QLineEdit` command bar. A pre-built cross-platform binding that can
coexist with Qt in-process is the intended vehicle; a windowing/GL-context library
drives the standalone shell.

Phased plan (renderer):

| Phase | Goal | Status |
|---|---|---|
| 9.0 | Controller code Qt-free; `scene.py` Qt-free | done by design |
| 9.1 | `renderer/imgui_renderer.py` implementing `Renderer` via the GL-context library | future |
| 9.2 | Immediate-mode command console replaces the `QLineEdit` bar | future |
| 9.3 | Object-panel sidebar (tree node per object, color swatch) | future |
| 9.4 | World-space overlays via the backend draw list (replace `QPainter` labels) | future |
| 9.5 | Extract a `CameraState` dataclass; route mouse via the backend IO | future |
| 9.6 | Optional: embed the GL window in the Qt shell | future |

# Design constraints that apply now

These hold during all current ChiMOL work so the migration stays cheap (also in the
[ChiMOL profile](/plugins/profiles/chimol.md)):

1. No Qt in controller code (`MolView` and its mixins import without a
   `QApplication`).
2. `scene.py` stays Qt-free — `Geometry`/`SceneObject`/`Scene` are plain dataclasses,
   the shared contract for every backend.
3. All overlays go through `SceneObject(kind="text", ...)`; both the Qt/GL and
   offline raytracer backends render from the same scene.
4. `qtgl.py` is a thin translator — camera math, shader uniforms, event handling
   only; no business logic.
5. Avoid new `QPainter.begin(self)` uses (removed in phase 9.4).
6. New camera attributes go on simple fields for later extraction into a
   `CameraState` dataclass (phase 9.5).

# Relationships
- Forward roadmap for the plugin documented in the
  [ChiMOL profile](/plugins/profiles/chimol.md); the viewer is exposed as a
  structure/molecular-viewer tool in [Modelling plugins](/plugins/modelling.md) and
  scripted via `chimol-cli` ([Macros, CLI & scripting](/subsystems/macros-cli.md)).
- Manifest category drift is tracked as [assessment INC-07](/specs/assessment.md).
