---
type: Plugin Group
title: Trajectory tools
description: Molecular-dynamics trajectory utilities for alignment, conversion, joining, energy, FRET, clashes, transforms, and topology export.
resource: chisurf/plugins/traj/
tags: [plugins, structure, trajectory, molecular-dynamics]
timestamp: '2026-07-05T00:00:00Z'
---

The `traj/` group handles molecular-dynamics trajectory files and structure
series. It is part of the structural/modelling side of ChiSurf and complements
the [modelling plugins](/plugins/modelling.md) plus the
[structure model family](/subsystems/models.md).

| Plugin dir | Display name | What it does |
| --- | --- | --- |
| `traj_align` | Structure:Trajectory:Align | Aligns trajectories to a reference frame or structure. |
| `traj_convert` | Structure:Trajectory:Convert | Converts trajectory files between supported formats. |
| `traj_join` | Structure:Trajectory:Join | Joins or stacks trajectories. |
| `traj_rotate_translate` | Structure:Trajectory:Rotate/Translate | Applies rigid-body rotation and translation. |
| `traj_save_topology` | Structure:Trajectory:Save Topol | Saves topology or first-frame structure files. |
| `traj_remove_clashes` | Structure:Trajectory:Remove Clashed | Removes frames with steric clashes. |
| `potential_energy` | Structure:Trajectory:Energy Calculator | Computes potential-energy components for structures and trajectories. |
| `fret_trajectory` | Structure:Trajectory:FRET | Calculates FRET observables from molecular-dynamics trajectories. |

Each entry is its own **Structure › Trajectory** ribbon button and dock (no hub: the Traj Tools workspace was
removed 2026-10-19, owner: in emtk every tool is its own dock). Keep reusable structure/trajectory math outside widgets when
expanding this group so it can be called from scripts, services, and tests.

All eight single-tool `traj_*` widgets — `traj_save_topology`, `traj_align`,
`traj_join`, `traj_rotate_translate`, `traj_convert`, `traj_remove_clashes`,
`potential_energy` and `fret_trajectory` — have been migrated off their
hand-built `.ui` files onto the [AutoForm](/subsystems/gui-autoform.md)
pattern. Each now pairs a Qt-free view-model (holding the paths, options and a
running log, and doing all the trajectory/compute work through
`core/structure/trajectory_data.py`) with an `AutoForm` laid out
from a sibling `*.view.json`: a picker custom section (`<name>_io`, with
**trajectory and topology** browse rows, drag-drop and the `💾`/`▶` action
buttons — DCD and XTC store coordinates only, so the atom names come from a
PDB named separately) plus built-in `value`/
`choice`/`toggle`/`table` field sections over a live `info` log bound to the
model's `log_html`. Irreducibly-dynamic Qt (the `potential_energy` per-potential
parameter editor + potentials table) lives in bespoke `@register_section`
custom widgets that drive the Qt-free model. FRET now uses the declared native
form: four cascading chain/residue/atom rows replace its retired Qt selectors.

The view-models are unit-tested headlessly (each ships a `test/` with a
`test_view_model.py` running the real compute on realistic fixtures, plus a
`test_gui.py` with a construction/delegation test, a rendering test, and — for
`potential_energy`/`fret_trajectory` — a qtbot **GUI-interaction functional
test** that drives the actual widgets and asserts a computed result). All `.ui`
files are retired. The migration also fixed several latent bugs (see
`okf/log.md`, 2026-07-22): `traj_align`/`traj_rotate_translate` wrote to a
non-existent HDF5 node, `traj_rotate_translate`'s save dialog was never wired,
`traj_join` carried a dead `stride` property, and `fret_trajectory` both accessed
an un-imported `kappa2` submodule and reset its atom selection mid-compute on a
form refresh.

See also [modelling plugins](/plugins/modelling.md), [compiled modules](/subsystems/compiled-modules.md),
and [plugin system](/architecture/plugin-system.md).


## Traj Tools hub removed — 2026-10-19

`chisurf/plugins/traj/traj_tools/` (manifest, `CalculatorHubApp` subclass, registry, strings, tests, renders) is
gone with no shim; the eight tools lost `menu_hidden`. What the hub carried besides the list moved into each tool's
`help.md` ("Example data and the other trajectory tools": the `olga_t4l` T4L ensemble and the Align → Remove
Clashed → FRET order); drop routing and settings persistence were already each tool's own. Icons made distinct for the
shared ribbon group: Convert ♻️, Energy Calculator 🔋, Join 🧷. The guide-81 figures are drawn per tool
(`make_screenshots.py::_grab_traj_tools`). Open: the ribbon labels follow the old display names (`Save Topol`,
`Remove Clashed`); renaming them is a manifest edit plus `test_ribbon_layout.py::EXPECTED`.

## Native FRET host retirement — 2026-10-07

The FRET manifest and standalone launcher use FretTrajectoryApp. The remaining
Qt trajectory workspace hosts that same app and closes only its owned FRET
surface once. Twelve cascading selectors become four native rows; scientific
parameters and116×6 reference bytes are preserved. PDBSelector and the legacy
FRET widget/sections retire.69 targeted tests and665 contract checks pass; real
before/after and clean-close renders inspected.
