---
type: Plugin Group
title: Modelling plugins
description: Structural and FRET-modelling tools — accessible-volume editing, restrained rigid-body docking, orientation-factor and hydrodynamics estimation, and FRET-line generation.
resource: chisurf/plugins/modelling/
tags: [plugins, modelling]
timestamp: '2026-10-12T00:00:00Z'
---

## Where to pick this up (2026-10-26: the FPS JSON editor plugin is gone, the editor is ChiMOL's)

1. **Structure tab layout** is Modelling (ChiMOL) · FRET (Docking & Screening) · Computation
   (HydroPro, QuEst) · Trajectory (Traj Tools), from `GROUP_ORDER["Structure"]` in
   `chisurf/core/plugin/ribbon_layout.py`. Re-derive with `test/plugins/test_ribbon_layout.py`; the Qt reference
   inventories (`test/native_emtk/shell_{s5,whole}_qt_inventory.json`) had only their Structure parts re-captured
   (the scripts rewrite the WHOLE file — splice, do not overwrite: other tabs carry other lanes' baselines).
2. **Measure: the fps.json editor lives in ChiMOL only** (owner 2026-10-26, dedup). The `modelling/fps_json_editor`
   plugin is deleted; its second document model (`FpsJsonModel`), payload checks, naming and colour helpers were
   duplicates of chimol's `labelling/fps.py` / `editor.py` and are merged there (chimol `d31ca8b`: cascading
   removes, gzip, relative `pdb_path`, `validate/summarize/normalize_payload`, CLI `chimol-fps`, the tour's
   Load-example step `fps_load labelling_example.fps.json`, 'What to check' help, de/fr). ChiSurf reaches it as
   ChiMOL › Tools › Labelling (the ChiMOL host's `commands=` still opens it on a panel); the window's own Guide
   (`tour fps_editor`) and ? come with it. The headless RPC moved to the ChiMOL host:
   `chimol.fps.validate|summarize|normalize`, `chimol.pdb.fetch`, `chimol.av.mrc.save`
   (`chisurf/plugins/chimol/rpc.py`). ProteinMC's fps.json readers kept their tests
   (`proteinmc/test/test_fps_json_readers.py`). Before/after renders of the editor are control-for-control
   identical (same code); deliberate difference: no ribbon button of its own.
3. **`test_plugin_help_guide_seam` / `demo_contract_audit` read HEAD**: until this change is committed they still
   see `structure_tools` (failures "GUI module not on disk: structure_tools") — not a defect of the tree.
4. **FRET window** (`fret/gui/app.py`) is a two-tool window of its own (docking + pair selection); Pair Selection
   could become its own ribbon entry if the owner wants the same "normal tool" rule there.
5. Shared card shell: `chisurf/emtk/card_shell.py` (`CardShell`, `Rows`) — used by the docking, pair-selection and
   QuEst cards.
6. **AV obstacle radii are one set (owner, 2026-10-12): IMP's radii × `AV_DEFAULT_RADIUS_SCALE` (0.84).** See
   "Accessible-volume obstacle radii" below. Guard: `test/core/test_av_single_radius_set.py`. Open: IMP.bff's file
   door reads **every** PDB record (waters and HETATM at IMP's 1.7 Å default) while the structure door drops waters —
   same radii, different atom sets; decide whether the file door should drop waters too.

## Accessible-volume obstacle radii (one set)

Every AV door takes the obstacle radius of an atom as **IMP's radius for its residue and atom name** (the all-atom
CHARMM radius `IMP::atom::read_pdb` assigns; IMP's 1.7 Å default for an untyped atom) **times
`IMP.bff.AV_DEFAULT_RADIUS_SCALE`**. In the IMP-free `imp-bff` wheel ChiSurf runs on, IMP's mapping is
`IMP.bff.imp_atom_radius` (a table regenerated from IMP, held equal to `read_pdb` by IMP.bff's
`test/representation/test_imp_atom_radii.py`); `IMP.bff.load_structure_with_vdw` / `get_av_from_pdb` apply it
with the scale. ChiSurf's one accessor is `chisurf/core/structure/av/radii.py` (`radius_scale`, `imp_radii`,
`obstacle_radii`, `obstacle_xyzr`), used by `core/structure/av` (`BasicAV`/`ACV`/`DynamicAV`: radii from the
atoms' residue and name, *not* the structure's `radius` column, which is whatever its reader chose) and by the
FRET plugin (`modelling/fret/core/av.py`, trajectory evaluation in `core/evaluate.py`). QuEst reads IMP's particle
radii and scales them itself (same numbers). The FRET plugin's Bondi `VDW_RADII` table (FPS's `vdW.txt`) is gone;
so is chimol's copy (`chimol/plugins/labelling/av.py`). Bondi element radii remain only where they are not AV
obstacles: the molecular viewer's element table (`core/fio/structure/elements.py`) and IMP.bff's Labelizer surface areas.

The modelling group turns fluorescence observables (FRET efficiencies, anisotropies,
diffusion coefficients) into and out of molecular structure. Most tools live under
`chisurf/plugins/modelling/`; two closely related FRET-modelling plugins
(`fret_line` at the plugin root, `calculator/kappa2_dist` under the calculators group)
belong to the same domain. There is no structure hub: every tool is its own ribbon
button on the Structure tab (the `structure_tools` hub was dissolved 2026-10-12; its cards
moved into the plugins that own them, the shared window shell into `chisurf/emtk/card_shell.py`).

| Plugin dir | Display name | What it does |
| --- | --- | --- |
| `modelling/fret` | Structure:FRET:Docking & Screening | One window with the docking card (`gui/docking_card.py`, session `gui/docking_session.py`) and the pair-selection card. FRET-restrained rigid-body docking, refinement, structure-library screening and error estimation; a thin shim around an external molecular-modeling framework and its accessible-volume/FRET extension. |
| `modelling/hydropro` | Structure:Computation:HydroPro | Graphical front-end to an external hydrodynamics tool, computing properties such as the translational diffusion coefficient from atomic or bead-model structures. |
| `modelling/proteinmc` | (no manifest) | Protein Monte-Carlo helpers; a first-class module still lacking a `manifest.json` (see steering note). |
| `fret_line` | Spectroscopy:FRET:FRET Line Generator | Compute static, dynamic, WLC and mixture FRET lines for overlay on smFRET 2D histograms in ndxplorer. |
| `calculator/kappa2_dist` | Tools:Calculators:Kappa2 Distribution | Compute and visualise the κ² orientation-factor distribution (WIC, DWT, isotropic models); lives under the calculators group and is embedded in the calculators hub. |

Integration follows the standard plugin contract ([plugin system](/architecture/plugin-system.md),
[Plugins target](/specs/plugins.md)): each plugin is discovered by its `manifest.json`,
activated with a `PluginContext` that exposes the API facade for datasets/fits, and
renders its panels declaratively through [GUI & AutoForm](/subsystems/gui-autoform.md).
`fret_docking` persists FPS-style pose vectors and reloads projects to continue a run.
Note `modelling/proteinmc` currently has no manifest — a documented gap against the
one-manifest-identity rule in [Plugins target](/specs/plugins.md).

## FRET docking engine (durable facts)

The `modelling/fret` engine keeps all computation in importable, GUI-free core
modules (`av.py`, `clash.py`, `distance.py`, `engine.py`, `docking.py`,
`screening.py`, `results.py`, `io.py`), with thin `cli/` (click) and `gui/`
(`wizard.py`) layers on top — the design intent is that the plugin is a strict
**superset of the legacy FPS + OLGA** tools. Load points to keep stable:

- **AV backends are selectable.** `av.py` computes accessible volumes via an
  external labelling library (primary) with a biophysical-modeling-framework
  fallback; `select_backend(name)` and an `--av-backend auto|…` flag pick between
  them, gated by availability flags. The fallback AV path is unavailable on
  Windows and must skip gracefully.
- **`fps.json` is the interchange format.** Never rename its keys (`Positions`,
  `Distances`, `χ²`); multi-body docking carries a `body_id` per position and
  evaluators serialize under an `Evaluators` key. The labelling UI and the
  document model are ChiMOL's (`chimol.plugins.labelling`: `FpsModel`, the editor,
  `chimol-fps`); ChiSurf keeps no copy.
- **Evaluators** live in `fret/evaluators/` (positions, distance, fret_efficiency,
  chi2, residuals, geometry, av_metrics), all deriving from an `Evaluator` ABC
  with JSON round-trip and DataFrame/CSV export.
- **Informative pair selection** reuses `chisurf/plugins/traj/fret_pair_selection/
  olga_greedy.py` (`select_informative_pairs`) and emits OLGA-compatible reports.

The in-tree `TARGETS.md` and the draft "FRET superset" plan (refine/bootstrap,
sampling fix, OLGA evaluator graph) are captured as [PRD-58](/prds/prd-58.md); the
evaluator subpackage has already landed. The [ChiMOL viewer](/plugins/profiles/chimol.md)
roadmap is [PRD-57](/prds/prd-57.md).

## Idea: structure-aware MMFDB sample definer

ChiMOL's labelling editor (`chimol.plugins.labelling`) already implements most of what a flrCIF-grade sample definer
needs — PDB loading, atom-level position picking, accessible-volume simulation,
and distance restraints. Its parts (the positions table, the AV computation, the distance table)
are reuse candidates for a future `sample_definer` that produces MMFDB
`SampleDefinition`/`ProbeDefinition`/`FretPairDefinition` records (a structure-aware
replacement for the flat sample picker), auto-filling AV parameters and
photophysics from the fluorophore database and computing R0 from spectral overlap.
The cleanest path composes those parts into a new host rather than modifying
the editor; this feeds the sample-tracking work in
[PRD-02](/prds/prd-02.md), [PRD-06](/prds/prd-06.md) and [PRD-08](/prds/prd-08.md).
