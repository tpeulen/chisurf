# fcs_toolbox (FCS hub) and fcs_correlator — emtk port report

**Accepted** 2026-10-05. The ribbon's **Spectroscopy → FCS** opened the Qt `FcsTool` (a script entry, so the
dual-entrypoint audit never saw it). Both manifests now declare `gui` (the Qt tool, kept as the fallback) and `emtk`;
auto mode opens the native hub. The owner's report that started this: "fcs tools (FCS) opens the qt tool".

## What was built

- **Qt-free models and workflow.** `fcs_correlator/correlator_model.py` and `filter_model.py` hold the settings and
  computation that `correlator_panel.py` / `filter_panel.py` had mixed with Qt. The panels keep only their Qt sections;
  the Qt correlator adds back its progress dialog. `workflow.py` (`FcsWorkflow`) is the hand-over between the steps,
  which the Qt `FcsCorrelatorTool` performed in its own methods: the setup's channels, the ticked files expanded,
  LUT-aware TTTR reading, the filtered photons, and the merger's input. The Qt tool now delegates to it, so both front
  ends share one implementation.
- **Shared hub.** `chisurf/emtk/tool_hub.py` (`ToolHubApp`) is the native `NavigationPanelTool`:
  - a searchable rail with group captions, and the ⚠/⛔ maturity markers and banners read from the plugins' manifests;
  - workflow hooks: `panel_enabled` (a switched-off step is grey and skipped) and `on_select` (the hand-over);
  - **Next** runs the open step's `run_step()` and then advances; **>>** walks the rest of the group, waiting for each
    step, and a second press stops it;
  - Back, Help, Guide, Tool help;
  - input routed to the open tool, also while a tour is shown (only the tour card and help windows take it away).

  `tttr_toolbox` has its own copy of this hub (another stream's open edits); moving it onto `ToolHubApp` is on the
  roadmap.
- **Steps** (`fcs_correlator/gui/steps.py`):
  - **Files & Steps**: a checkable list with Files..., Folder..., Database, **Example**, All, None, Remove and Clear;
    the filter and merger switches; a `.bst` file switches the filter off.
  - **Photon / Burst Filter**: the same mode-pruned `filter.view.json`, the kept-photon count, the dT scatter with
    draggable min/max dMT lines, and the count rate; the body scrolls.
  - **Correlator**: the `correlator.view.json` controls, with native FCS preset / A-B / lifetime-filter /
    Correlate-Stop drawers, the correlation plot, and the work on a worker.
  - **Channel Definitions** and **FCS Merger** are the accepted `fcs_channel_preset` and `fcs_merger` apps.
  - The five tools are their plugins' own accepted apps. Filter Calc receives the correlator's files as its mixed decay
    (and its micro-time binning), as in Qt.
- **Demo.** `fcs_correlator/demo.py`: a seeded simulation (molecules crossing the focus in 0.25 ms) written as
  SPC-130. Its known answer: G(0)≈2, half-decay near 0.5 ms, flat at 1 beyond about 1 ms.
- **Guides.** `fcs_correlator/guide.json` and `fcs_toolbox/guide.json`; every awaited step waits for the user's own
  press (Example, Correlate, rail rows). `fcs_correlator/help.md` is new.

## Acceptance gate

1. **Functional**: `fcs_correlator` + `fcs_toolbox` + help/guide seam + preview gate + parity tool: **336 passed**
   (the one failure was two stale allow-list lines, `acq` / `wizards`, now struck). Then
   `test_emtk_workflow.py`: **15 passed**.
2. **Real interaction**: `fcs_correlator/test/test_emtk_workflow.py`, presses at drawn rects and typed keys:
   - Example → Correlator → typed channels and splits → Correlate → Next → Merger, at 1200x800 and 800x600;
   - the step switches (grey, skipped, unopenable), and a typed min photons changing what the correlator gets;
   - the file list: drop, tick, All / None, Remove, Clear, the Folder and Files dialogs, Database;
   - a `.bst` file switching the filter off;
   - lifetime filters (dialog), species A/B, Unload, a preset combo pick, and the Filter Calc jump;
   - SPC-132 correlating to the same numbers as the Qt model;
   - every step and tool opening with its controls inside the window;
   - the filter scrolling to its last plot at 800x600;
   - Help, and a guide walked by the user's own presses;
   - the correlator-only entry;
   - Filter Calc receiving the files, and the maturity markers;
   - Next and >>.
3. **Parity inventory**: `before.json` is the Qt `FcsTool` with every row visited and SPC-132 correlated
   (`scripts/capture_qt.py`, 274 controls); `after.json` is the same state in the native hub
   (`scripts/capture_emtk.py`, 378). `compare.json`: `lost: []`, `untooltipped: []`, Qt-free. `deliberate.json`
   explains 114 entries:
   - 80 controls belong to the hosted tools, each pointing at that tool's own accepted report;
   - the rest are combo options, folded-panel fields, axis ticks, placeholder texts of rows not yet built, and the
     Qt hub's own merger panel replaced by the accepted merger app.
4. **Visual**: `after_<row>_{1200x800,800x600}.png`, read. The numbers match Qt: the filter keeps 96,774 / 183,657
   (52.7%), and the correlation curves are identical. The native filter also draws the dT plot that the Qt panel left
   empty.
   - Fixed while reading: the filter overflowed 800x600 with no scrollbar (now a padded scrolling body); the
     correlator's filter buttons were clipped (now wrapping); "Controls" was captioned twice.
5. **Deltas**: `deliberate.json`. Behaviour delta: in Qt, Next and ⏩ only walked the FCS steps (no FCS panel has the
   shell's `toolAction_run`). Natively, Next runs the Correlator's Correlate, which is what Qt's own tooltip promised
   ("process all loaded files in this step, then go to the next step").

## Found on the way

- `burst_fcs_correlator/test/test_emtk_burst_fcs_clicks.py`: 2 tour tests fail on clean HEAD and on the working tree
  with the pre-change emtk. That plugin has ten files with another stream's uncommitted edits; reported on the board.
- Guide 75 (`docs/guides/75_fcs_toolbox.md`): figures regenerated from the native hub in the states their captions
  describe (`scripts/capture_docs.py`). The filter caption's "52.7 %" was wrong for its own settings (≥ 30 photons,
  ≤ 0.5 ms keep 21.7 %) and is corrected.
