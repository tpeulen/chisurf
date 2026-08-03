# Burst Fusion

Merges the bursts one molecule produced. A burst search sees only a count rate,
so a molecule that dims mid-passage — to the edge of the volume and back, an
acceptor blink — leaves two or three bursts where there was one molecule. This
step decides which consecutive bursts belong together from the recurrence
same-molecule probability `P_same(τ) = 1 − 1/G(τ)`, and writes the result as a
**new** burst-analysis folder that every later step reads unchanged. It is an
optional step of the burst pipeline, placed after burst selection and before
everything that measures a burst.

## Status

| Field | Value |
| --- | --- |
| Plugin id | `burst_fusion` |
| Menu path | `Spectroscopy:Single-Molecule:Burst Fusion` (`menu_hidden`; reached as step 3 of Burst Analysis) |
| Category | Spectroscopy, Single-Molecule |
| Maturity | `active` |
| Architecture | `client-server` + `declarative-ui` (Qt-free core, RPC service, AutoForm view) |
| MMFDB | `none` — results are files beside the data; provenance is the folder's own `Info/analysis.json` |

## User Workflows

1. **Judge a threshold before applying it.** Point the tool at a burst folder,
   press ▶ Run: the `P_same` curve, the window your threshold implies and the
   before/after burst statistics appear. Nothing is written.
2. **Write the fused folder.** Press 💾 Save. The photon streams are reopened and
   every column re-derived over the fused span. In the Burst Analysis window this
   also redirects the later steps to the new folder.
3. **Learn it without data.** 🧪 Load demo simulates a measurement in which 300
   molecules crossed the focus and ~60 % of the crossings were cut up, runs the
   real burst search over it, and loads the result — so the tour can be walked,
   and the answer checked against a declared number.
4. **Headless.** `csc fusion curve` reports; `csc fusion fuse` writes; both take
   the same options. `burst_fusion.jobs.analyze` / `.fuse` do the same over RPC.

## Inputs And Outputs

| Kind | Formats | Notes |
| --- | --- | --- |
| Input | a burst-analysis folder (`bi4_bur/*.bur`) | Accepts the analysis folder, its `bi4_bur` directory, or any folder of `.bur` files. |
| Input | the raw TTTR measurements the folder points into | Required for writing: the fused table is re-derived from the photons. Read through `staging.open_tttr`, so LUTs and micro-time shifts apply as everywhere else. |
| Input | `Info/analysis.json` (reading manifest) | Supplies the detector/window definition and container type. A folder without one needs them passed explicitly (`--detectors`, `--setup`, or the workflow's channel page). |
| Output | `<source>_fused_p<threshold>/bi4_bur/<stem>.bur` | A burst folder in every respect; the threshold is in the name so a second run cannot overwrite the first. |
| Output | `<fused>/fu4/<stem>.fu4` | Per fused burst: `Fused Bursts`, `Fused Gap Photons`. |
| Output | `<fused>/Info/fusion.json`, `Info/analysis.json`, `Info/*.mti` | The run (settings, window, curve, statistics) and how the raw data was read. |
| Output | `<source>/fg4/<stem>.fg4` *(optional)* | Beside the **original** bursts: `Fusion Group`, `Fusion Group Size`, `Fusion Lag (ms)`. The source `.bur` files are never modified. |

Both companions follow the
[burst-companion contract](../../../../okf/subsystems/burst-companions.md):
directory ending in `4`, one row per burst in table order, unique column names.

## UI Surface

A `ChisurfDockTool` hosting one AutoForm (`gui/fusion.view.json`):

- **Left** — the burst folder, the same-molecule threshold, the gap ceiling, the
  fragment cap, the two actions, a live status block (with the demo's declared
  truth when a demo is loaded), the before/after summary table, and a collapsed
  panel of `P_same` estimation settings.
- **Right** — dock tabs: the `P_same` curve with the threshold and fused window
  marked, proximity ratio, photons per burst, burst duration, and fragments per
  fused burst. All before/after overlays; after writing they show the *emitted*
  bursts rather than the preview, and the legend says which.
- **Toolbar** — 🧪 Load demo, Guide (`gui/guide.json`), ? (`gui/help.md`).
- The dock arrangement persists under the `burst_fusion` state namespace.
- The primary action carries the canonical `toolAction_run` object name, so the
  workflow shell's *Next ▶* drives this step like any other — and deliberately
  only *analyses*, because the step is optional.

## API, CLI, And RPC

| Surface | Entry point / method | Purpose |
| --- | --- | --- |
| Python API | `core.fusion.analyze(folder, settings)` | Decide the grouping and the statistics; writes nothing. |
| Python API | `core.fusion.write_fused_analysis(analysis, …)` | Write the fused folder from an analysis. |
| Python API | `core.fusion.fuse_folder(folder, settings, …)` | Both, in one call. |
| Python API | `demo.create_demo()` | Generate (or reuse) the demo measurement + burst folder. |
| CLI | `csc fusion curve FOLDER [--threshold …] [--json]` | Report what a threshold would do. |
| CLI | `csc fusion fuse FOLDER [--output …] [--detectors/--setup …]` | Write the fused folder. |
| RPC | `burst_fusion.jobs.analyze` | Curve + statistics for a folder. |
| RPC | `burst_fusion.jobs.fuse` | Write the fused folder. |
| RPC | `burst_fusion.workflow.prepare` | Resolve folder + detectors from a workflow context. |
| RPC | `burst_fusion.contract.describe` | The contract in `api/contract.py`, at run time. |

## Architecture

- `api/models.py` — `FusionSettings`, `MeasurementFusion`, `FusionAnalysis`.
- `api/contract.py` — method names, payload/result schemas, service envelopes.
- `core/fusion.py` — Qt-free: read a burst folder, group, preview, write the
  fused folder and its companions. Builds on
  `chisurf.core.fluorescence.burst.fusion` (the window rule, the grouping and
  the table merge) and `…burst.recurrence.pair_statistics` (the estimator shared
  with RASP).
- `backend/services.py` — RPC handlers; database-free, Qt-free.
- `cli/main.py` — `csc fusion`.
- `gui/` — view model (Qt-free), the AutoForm view spec, one custom section (the
  action bar), the guided tour and the help page.
- `demo.py` — the simulated measurement, generated through the real burst search.
- `tests/` — core round trip, companion contract, CLI, GUI, demo.

Known rule break: none. `core/` imports no Qt and no server code; `gui/` holds no
analysis logic beyond selecting what to plot.

## MMFDB And Provenance

The plugin does not read or write MMFDB. Provenance travels with the folder: the
fused analysis carries a reading manifest (`Info/analysis.json`) naming the raw
sources, the container type and the resolutions, plus `Info/fusion.json` with the
settings, the window, the `P_same` curve and the run statistics — enough to
reproduce the folder or to explain it later.

## Verification

```bash
# core: the window rule, pooling, transitive grouping, the table merge
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
  python -m pytest test/fluorescence/test_burst_fusion.py

# plugin: folder round trip on a real burst analysis, companions, CLI, GUI, demo
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
  python -m pytest chisurf/plugins/burst/burst_fusion/tests/

# the step's place in the pipeline
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
  python -m pytest chisurf/plugins/burst/burst_analysis/tests/test_workflow.py
```

Manual check: 🧪 Load demo, then thresholds 0.9 / 0.7 / 0.5 — the burst count
should move from ~428 through ~300 (the declared truth) to ~283, and the
proximity-ratio width should fall monotonically.

## Limitations And Open Work

- Fusion is decided from burst *arrival times* only. A photon-level criterion
  (do the fragments share a lifetime, an anisotropy, a stoichiometry?) would
  separate a recurrence from a coincidence far better at high concentration.
- The window is estimated once per folder (or once per measurement); it does not
  adapt to a drifting burst rate within a measurement.
- The fused burst is a *span*, because a `.bur` row is one photon interval. A
  representation that could exclude the inter-fragment photons would need a
  format change, and every downstream reader with it.
- No MMFDB registration of the fused folder yet.

## Related Files

- `manifest.json`
- `api/models.py`, `api/contract.py`
- `core/fusion.py`, `demo.py`
- `backend/services.py`, `cli/main.py`
- `gui/fusion.view.json`, `gui/view_model.py`, `gui/tool.py`, `gui/sections.py`,
  `gui/guide.json`, `gui/help.md`
- `tests/test_fusion.py`, `tests/test_cli.py`, `tests/test_gui.py`, `tests/test_demo.py`
- Theory: [`docs/concepts/burst_fusion.md`](../../../../docs/concepts/burst_fusion.md)
- Workflow: [`docs/guides/58_burst_fusion.md`](../../../../docs/guides/58_burst_fusion.md)
