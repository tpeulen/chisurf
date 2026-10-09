---
type: Report
title: EMTK plugin migration inventory
description: Dated inventory of plugin GUI entrypoints, native and legacy source boundaries,
  test coverage indicators, migration lanes, and required parity evidence.
---

# EMTK plugin migration inventory

Snapshot: 2026-09-27. This is a source inventory, not evidence that any plugin has passed its migration acceptance checks. Existing uncommitted work is included.

## Where to pick this up

1. Measure: Re-derive native launch and embedding behavior through `app.draw(PixelPainter, ...)` and `ControlHost(factory())`, as in the recorded audit. Calling `app.gui()` alone bypasses hub child selection and can produce a false pending page.
2. Open: Use the recorded hand-drawn-form findings to scope the shared tool scaffold and spec conversion; handwritten label columns and tooltip bookkeeping were the identified source of panel drift.
3. Measure: Check exact numeric entry and slider discoverability against the recorded calculator behavior before changing deliberately selected slider defaults.
4. Measure: Revalidate `test_the_demo_is_a_readable_ptu_whose_flow_comes_back` and inspect the recorded `ChiSurf_DemoFrames` header change first; the historical `n_escaped == 25` result is not a new run.
5. Open: Remove the recorded unused palette constants when their owning files are next touched, preserving the actual Run/Stop accent colors.
6. Tried and reverted: Contact-sheet labels and crops produced three false clipping/overlap findings. Judge the original full-size PNGs; the audit chronology and measurements are retained below.

## Recorded history and follow-up details

Audit of 2026-09-30 (headless render of every `entrypoints.emtk` factory, then the same route ChiSurf uses: `ControlHost(factory())`). Re-derive with a loop over manifests calling `app.draw(PixelPainter, ...)` -- **not** `app.gui()`: hub apps (`filetools`, `games`, `imaging_tools`) pick their child inside `ImApp.draw`, so `gui()` shows a false "panel pending" page.

1. **Tools are still hand-drawn, not specs.** ~60 `gui/app.py` files (2166 lines in `burst_selection`, 1097 `fcs_filter_calculator`, 883 `tttr_microtime_shifter` ...) draw forms with `im.text` + `same_line(col_x)` + `drag_float`, plus per-control `remember()`/`track()`/`set_item_tooltip` boilerplate (see `burst_bva/gui/app.py`). Only ~10 use a `*.view.json`. What it blocks: every control needs a hand-set label column and tooltip, so panels drift (labels above vs beside, status boxes filling half the sidebar). Next step: a shared emtk "tool scaffold" (toolbar Run/Stop/Guide/Help + `ViewSpecPanel` + plot area + status line + guide targets from spec names) so a burst tool is a spec and a plot function.
2. **Numeric parameters are sliders.** Most spec/`SettingsModel` numbers with bounds become `slider_*` with the value centred in the track (`psf_calculator`, `fcs_calculator`, `fret_line`); exact entry is Ctrl+Click or double-click. For scientific values (refractive index, fit windows) a drag/field with a wide range is the better default. Done for discoverability: a double click on a slider now opens the type-in (emtk, uncommitted with the other stream's `im_widgets.py`). The slider stays the default -- `calculator/inputs.py` chose it on purpose, with log tracks for wide ranges.
3. **`img_flow` demo**: `test_the_demo_is_a_readable_ptu_whose_flow_comes_back` gets `n_escaped == 25`; `img_flow/demo.py` carries an uncommitted new `ChiSurf_DemoFrames` header tag from another stream -- check that first.
4. Dead palette constants (`WINDOW_BG`, `PANEL_BG`, `ACCENT_*`) sit in ~20 `gui/app.py`; only Run/Stop accent colours are drawn. Remove with the next touch of each file.
5. Tried and rejected: contact-sheet labels and crops made three false "overlap"/"clipped text" findings; judge from the full-size PNG, not the sheet.

## Scope and findings

Actual manifests: **133**; Native factory declarations: **100**; GUI entrypoints: **117**; additional legacy script entrypoints: **11**.

- `qt_or_other_gui_requires_port`: 13
- `emtk_surface_qt_runtime_or_adapter`: 8
- `legacy_script_requires_gui_audit`: 7
- `native_factory_declared_requires_full_audit`: 100
- `external_gui_requires_audit`: 1
- `no_gui_entrypoint`: 5

110 plugins have local tests; 117 have local tests or explicit plugin import references in the repository test tree. Tests were not executed for this inventory. 38 GUI plugins have no local Python tooltip markers.

Declared `entrypoints.emtk` factories are recorded separately; declaration does not prove import purity, complete workflows or test acceptance. Legacy Qt source files retained as references remain in the per-plugin source lists and are not automatically part of the native factory runtime. An EMTK app rendered inside `ChisurfDockTool` or `emtk.qt_host.ControlHost` is not a pure EMTK entrypoint. `app.py` existence is not functional parity. Qt imports listed below include adapters and optional imports; no claim is made that every listed file is reachable from the selected entrypoint. A transitive import audit must additionally inspect shared widgets, launchers, third-party viewers, `__init__.py`, dynamic imports and backend modules. Tooltip markers prove only that some tooltips exist, not coverage; JSON/view-spec/shared helper tooltips may be absent from this Python scan.

## Required acceptance for every GUI plugin

- Capture the current Qt interface with representative data, tabs, dialogs, context menus and error states before replacement. Store screenshot paths and scenario metadata. Hidden/deprecated plugins remain in scope until explicitly retired.
- For each port, capture a populated native screenshot at the normal and narrow window sizes and compare it with the matching Qt reference using the visual-verdict workflow. Require a score of **90 or higher**; if it scores lower, revise the layout and re-run the comparison before marking the plugin visually accepted.
- Record actions, state/persistence, data import/export, scientific result equivalence, plots, selection, keyboard navigation, context menus and lifecycle behavior; test each preserved workflow.
- Audit existing EMTK surfaces with the same matrix. Remove Qt entrypoint and transitive runtime requirements, retaining reference implementations only outside the production launch path.
- Cover every interactive control with a meaningful tooltip, including icon buttons, tabs, dock controls and disabled controls. Check tooltips on screenshots/UI behavior, not just source markers.
- Exercise actual GUI launch and representative workflows; record tests executed and screenshot evidence. A green factory render is only launch evidence; it does not pass the screenshot, workflow or feature-parity gates. Fix shared EMTK defects in EMTK with reusable regressions.
- Legacy script entrypoints may launch GUI tools even without a `gui` field and need the same GUI audit. CLI/service-only manifests need import and backend tests, but do not need an invented GUI.

## Bounded execution lanes

1. Shared infrastructure: standalone EMTK plugin launcher/window lifecycle, file dialogs, tooltips, dock/tab controls and Qt-free imports. Resolve this before removing adapters across plugins.
2. Existing calculator and TTTR EMTK apps: audit feature parity and tooltips, switch manifest launch targets to standalone EMTK, test science/IO and capture references.
3. Burst suite: existing apps have broad Qt-adapter dependencies; split launcher/base and individual workflow parity work.
4. Core tools: code editor and help are EMTK surfaces with optional Qt hosts; then settings, project/database/plugin/model managers and setup workflows.
5. FCS and fluorescence decay: build parity matrices around correlator/fitting/filter workflows and backend outputs.
6. Microscopy: shared imaging/MLE infrastructure first, then individual tools, data selection and plotting.
7. Trajectory/modelling/external viewers: shared structure/trajectory IO and native viewer integration; ChiMOL and ndXplorer require external-package audits.
8. Games and remaining standalone utilities: preserve controls and keyboard interaction; low scientific risk but still complete tooltip and lifecycle checks.

## Per-plugin ledger

Full file lists and entrypoints are in [the JSON inventory](emtk-migration-inventory.json). `Tests` counts local files plus external test references; tests may overlap and do not prove coverage. All parity/screenshot/testing acceptance flags start unverified.

| Plugin | GUI entrypoint | Source status | Qt files | EMTK files | Tooltip files | Tests |
|---|---|---|---:|---:|---:|---:|
| `ai_settings` | `chisurf.plugins.ai_settings.gui.tool:AISettingsWidget` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 2 |
| `accurate_fret` | `chisurf.plugins.burst.accurate_fret.gui.tool:AccurateFretTool` | native_factory_declared_requires_full_audit | 1 | 2 | 2 | 2 |
| `alex_suite` | `chisurf.plugins.burst.alex_suite.gui.tool:AlexSuiteTool` | emtk_surface_qt_runtime_or_adapter | 4 | 4 | 1 | 5 |
| `bid_to_analysis` | `script: __init__.py` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 2 |
| `burst_2cde` | `chisurf.plugins.burst.burst_2cde.gui.tool:BurstTwoCdeTool` | native_factory_declared_requires_full_audit | 1 | 3 | 2 | 6 |
| `burst_analysis` | `chisurf.plugins.burst.burst_analysis.gui.tool:BurstAnalysisTool` | emtk_surface_qt_runtime_or_adapter | 2 | 4 | 3 | 9 |
| `burst_background` | `chisurf.plugins.burst.burst_background:BurstBackgroundEstimator` | native_factory_declared_requires_full_audit | 3 | 3 | 3 | 5 |
| `burst_browser` | `chisurf.plugins.burst.burst_browser:BurstBrowserWidget` | native_factory_declared_requires_full_audit | 3 | 3 | 3 | 3 |
| `burst_bva` | `chisurf.plugins.burst.burst_bva.gui.tool:BVATool` | native_factory_declared_requires_full_audit | 1 | 3 | 2 | 9 |
| `burst_ebfret` | `chisurf.plugins.burst.burst_ebfret.gui.tool:EbfretTool` | emtk_surface_qt_runtime_or_adapter | 1 | 3 | 1 | 8 |
| `burst_fcs_correlator` | `chisurf.plugins.burst.burst_fcs_correlator.gui.tool:BurstFcsTool` | native_factory_declared_requires_full_audit | 2 | 3 | 4 | 7 |
| `burst_fusion` | `chisurf.plugins.burst.burst_fusion.gui.tool:BurstFusionTool` | native_factory_declared_requires_full_audit | 2 | 3 | 4 | 7 |
| `burst_gs` | `chisurf.plugins.burst.burst_gs.gui.tool:BurstGsTool` | native_factory_declared_requires_full_audit | 1 | 3 | 3 | 4 |
| `burst_h2mm` | `chisurf.plugins.burst.burst_h2mm.gui.tool:H2mmTool` | emtk_surface_qt_runtime_or_adapter | 1 | 2 | 2 | 19 |
| `burst_irf_bg` | `chisurf.plugins.burst.burst_irf_bg.gui.tool:BurstIrfBackgroundTool` | native_factory_declared_requires_full_audit | 2 | 3 | 2 | 3 |
| `burst_mle_analysis` | `chisurf.plugins.burst.burst_mle_analysis.wizard:MLELifetimeAnalysisWizard` | emtk_surface_qt_runtime_or_adapter | 2 | 1 | 2 | 12 |
| `burst_selection` | `chisurf.plugins.burst.burst_selection.gui.tool:BurstSelectionTool` | emtk_surface_qt_runtime_or_adapter | 6 | 2 | 4 | 43 |
| `mfd_prepare` | `chisurf.plugins.burst.mfd_prepare.gui.tool:MfdPrepareTool` | emtk_surface_qt_runtime_or_adapter | 1 | 2 | 1 | 1 |
| `fcs_saturation` | `chisurf.plugins.calculator.fcs_saturation_calc.gui.tool:SaturationCalculatorTool` | native_factory_declared_requires_full_audit | 1 | 1 | 2 | 6 |
| `fret_calculator` | `chisurf.plugins.calculator.fret_calculator.gui.tool:FretCalculatorTool` | native_factory_declared_requires_full_audit | 2 | 2 | 1 | 4 |
| `calculators` | `chisurf.plugins.calculator.hub.gui.tool:CalculatorHub` | native_factory_declared_requires_full_audit | 2 | 1 | 2 | 1 |
| `kappa2_dist` | `chisurf.plugins.calculator.kappa2_dist.gui.tool:Kappa2Dist` | native_factory_declared_requires_full_audit | 2 | 2 | 1 | 8 |
| `phasor_calculator` | `chisurf.plugins.calculator.phasor_calculator.gui.tool:PhasorCalculatorTool` | native_factory_declared_requires_full_audit | 1 | 2 | 1 | 2 |
| `psf_calculator` | `chisurf.plugins.calculator.psf_calculator.gui.tool:PSFCalculator` | native_factory_declared_requires_full_audit | 1 | 1 | 2 | 1 |
| `rics_precision` | `chisurf.plugins.calculator.rics_precision.gui.tool:RicsPrecisionTool` | native_factory_declared_requires_full_audit | 1 | 2 | 1 | 3 |
| `chimol` | `chimol.hosts.qt:MolViewPluginWindow` | external_gui_requires_audit | 1 | 0 | 0 | 240 |
| `about` | `script: __init__.py` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 1 |
| `acq` | `chisurf.plugins.core.acq.gui.tool:SMAcquisitionManager` | qt_or_other_gui_requires_port | 14 | 0 | 6 | 7 |
| `batch_analysis` | `chisurf.plugins.core.batch_analysis.gui.tool:BatchProcessingWizard` | native_factory_declared_requires_full_audit | 4 | 0 | 1 | 3 |
| `boarding` | `chisurf.plugins.core.boarding.wizard:WelcomeToChiSurfWizard` | native_factory_declared_requires_full_audit | 3 | 0 | 0 | 3 |
| `code_editor` | `chisurf.plugins.core.code_editor.gui.tool:CodeEditorEmtkTool` | native_factory_declared_requires_full_audit | 8 | 4 | 9 | 10 |
| `database_connector` | `none` | no_gui_entrypoint | 0 | 0 | 0 | 2 |
| `f_test` | `chisurf.plugins.core.f_test.gui.tool:FTestTool` | native_factory_declared_requires_full_audit | 1 | 1 | 2 | 2 |
| `globalview` | `chisurf.plugins.core.globalview.gui:GraphWizard` | emtk_surface_qt_runtime_or_adapter | 2 | 4 | 0 | 3 |
| `help` | `chisurf.plugins.core.help.gui.tool:HelpEmtkTool` | native_factory_declared_requires_full_audit | 4 | 2 | 4 | 18 |
| `hmm` | `chisurf.plugins.core.hmm.gui.tool:HmmTool` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 1 |
| `lightpath_simulator` | `chisurf.plugins.core.lightpath_simulator.gui.tool:LightPathSimulatorWidget` | native_factory_declared_requires_full_audit | 2 | 1 | 2 | 8 |
| `menu_switch` | `script: __init__.py` | legacy_script_requires_gui_audit | 0 | 0 | 0 | 0 |
| `mmfdb_admin` | `chisurf.plugins.core.mmfdb_admin.gui.tool:MMFDBWidget` | qt_or_other_gui_requires_port | 18 | 0 | 8 | 30 |
| `model_manager` | `chisurf.plugins.core.model_manager.gui.tool:ModelManagerWidget` | native_factory_declared_requires_full_audit | 1 | 0 | 1 | 1 |
| `plot_settings` | `chisurf.plugins.core.plot_settings.gui.tool:PlotSettingsWidget` | native_factory_declared_requires_full_audit | 1 | 0 | 1 | 1 |
| `plugin_check` | `chisurf.plugins.core.plugin_check.gui.tool:PluginCheckTool` | native_factory_declared_requires_full_audit | 2 | 0 | 1 | 0 |
| `plugin_manager` | `chisurf.plugins.core.plugin_manager.gui.tool:PluginManagerWidget` | native_factory_declared_requires_full_audit | 3 | 0 | 2 | 2 |
| `project_browser` | `chisurf.plugins.core.project_browser.gui.tool:ProjectBrowserTool` | native_factory_declared_requires_full_audit | 1 | 0 | 1 | 5 |
| `pto_inspector` | `chisurf.plugins.core.pto_inspector.gui.tool:PtoInspectorTool` | native_factory_declared_requires_full_audit | 1 | 0 | 1 | 3 |
| `screenshot` | `script: __init__.py` | legacy_script_requires_gui_audit | 0 | 0 | 0 | 0 |
| `setup` | `chisurf.plugins.core.setup.gui.tool:UnifiedSettingsTool` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 0 |
| `setup_channel_definition` | `chisurf.plugins.core.setup_channel_definition.gui.tool:SetupChannelDefinitionWidget` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 0 |
| `style_manager` | `chisurf.plugins.core.style_manager.gui.tool:StyleManagerWidget` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 1 |
| `switch_user` | `chisurf.plugins.core.switch_user:SwitchUserWidget` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 0 |
| `tttr_to_pto` | `chisurf.plugins.core.tttr_to_pto.gui.tool:TttrToPtoTool` | native_factory_declared_requires_full_audit | 1 | 0 | 1 | 9 |
| `updater` | `chisurf.plugins.core.updater:UpdaterWidget` | qt_or_other_gui_requires_port | 3 | 0 | 1 | 6 |
| `user_editor` | `chisurf.plugins.core.user_editor.gui.tool:UserEditorWidget` | native_factory_declared_requires_full_audit | 1 | 0 | 1 | 1 |
| `wizards` | `chisurf.plugins.core.wizards.gui.tool:WizardHub` | native_factory_declared_requires_full_audit | 2 | 0 | 1 | 1 |
| `fcs_calculator` | `chisurf.plugins.fcs.fcs_calculator.wizard:ConfocalCalcWidget` | native_factory_declared_requires_full_audit | 1 | 1 | 2 | 4 |
| `fcs_channel_preset` | `chisurf.plugins.fcs.fcs_channel_preset.gui.tool:FCSChannelWidget` | native_factory_declared_requires_full_audit | 2 | 0 | 1 | 1 |
| `fcs_convert` | `none` | no_gui_entrypoint | 0 | 0 | 0 | 3 |
| `fcs_correlator` | `script: wizard.py` | legacy_script_requires_gui_audit | 4 | 0 | 2 | 3 |
| `fcs_filter_calculator` | `chisurf.plugins.fcs.fcs_filter_calculator.gui_parts.main_window:FcsFilterCalculatorWidget` | native_factory_declared_requires_full_audit | 5 | 1 | 3 | 4 |
| `fcs-lfcs-sim` | `chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool:LifetimeFcsSimWidget` | qt_or_other_gui_requires_port | 1 | 0 | 0 | 2 |
| `fcs_merger` | `chisurf.plugins.fcs.fcs_merger.wizard:ChisurfWizard` | native_factory_declared_requires_full_audit | 0 | 1 | 1 | 3 |
| `fcs_toolbox` | `script: __init__.py` | legacy_script_requires_gui_audit | 1 | 0 | 0 | 1 |
| `flc-2d` | `chisurf.plugins.fcs.flc_2d.gui.tool:FlcTwoDTool` | qt_or_other_gui_requires_port | 2 | 0 | 1 | 15 |
| `irf_estimator` | `chisurf.plugins.fluorescence_decay.irf_estimator.gui.tool:IRFEstimatorTool` | native_factory_declared_requires_full_audit | 1 | 1 | 2 | 3 |
| `lifetime_analysis` | `chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.tool:LifetimeAnalysisTool` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 1 |
| `lltf` | `chisurf.plugins.fluorescence_decay.lltf.lltf_gui:LLTFGUIWizard` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 7 |
| `maxent_decay` | `chisurf.plugins.fluorescence_decay.maxent_decay.gui.gui:MaxentDecayWidget` | native_factory_declared_requires_full_audit | 2 | 0 | 2 | 7 |
| `synthetic_decay` | `chisurf.plugins.fluorescence_decay.synthetic_decay.gui.tool:SyntheticDecayTool` | native_factory_declared_requires_full_audit | 2 | 1 | 1 | 3 |
| `tr_anisotropy` | `chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.tool:AnisotropyWizard` | native_factory_declared_requires_full_audit | 4 | 0 | 2 | 4 |
| `fret_line` | `chisurf.plugins.fret_line.gui.tool:FRETLineTool` | native_factory_declared_requires_full_audit | 2 | 1 | 2 | 3 |
| `clsm` | `chisurf.plugins.microscopy.clsm.gui.tool:CLSMPixelSelect` | native_factory_declared_requires_full_audit | 2 | 0 | 0 | 3 |
| `clsm_generator` | `chisurf.plugins.microscopy.clsm_generator.gui.tool:ClsmGeneratorTool` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 1 |
| `imaging_common` | `none` | no_gui_entrypoint | 2 | 0 | 1 | 4 |
| `imaging_tools` | `chisurf.plugins.microscopy.imaging_tools.gui.tool:ImagingToolsTool` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 0 |
| `img_calibration` | `chisurf.plugins.microscopy.img_calibration.gui.tool:ImgCalibrationTool` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 1 |
| `img_coloc` | `chisurf.plugins.microscopy.img_coloc.gui.tool:ImgColocTool` | native_factory_declared_requires_full_audit | 2 | 0 | 1 | 1 |
| `img_drift` | `chisurf.plugins.microscopy.img_drift.gui.tool:ImgDriftTool` | qt_or_other_gui_requires_port | 1 | 0 | 1 | 1 |
| `img_flow` | `chisurf.plugins.microscopy.img_flow.gui.tool:ImgFlowTool` | qt_or_other_gui_requires_port | 1 | 0 | 1 | 1 |
| `img_frc` | `chisurf.plugins.microscopy.img_frc.gui.tool:ImgFrcTool` | qt_or_other_gui_requires_port | 1 | 0 | 1 | 1 |
| `img_pixel_intensity` | `chisurf.plugins.microscopy.img_pixel_intensity.gui.tool:ImgPixelIntensityTool` | native_factory_declared_requires_full_audit | 0 | 0 | 0 | 1 |
| `img_pixel_micro_time` | `chisurf.plugins.microscopy.img_pixel_micro_time.gui.tool:ImgPixelMicroTimeTool` | native_factory_declared_requires_full_audit | 0 | 0 | 0 | 2 |
| `img_pixel_mle` | `chisurf.plugins.microscopy.img_pixel_mle.gui.tool:ImgPixelMleTool` | native_factory_declared_requires_full_audit | 0 | 0 | 0 | 3 |
| `img_pixel_nb` | `chisurf.plugins.microscopy.img_pixel_nb.gui.tool:ImgPixelNBTool` | native_factory_declared_requires_full_audit | 0 | 0 | 1 | 3 |
| `img_pixel_phasor` | `chisurf.plugins.microscopy.img_pixel_phasor.gui.tool:ImgPixelPhasorTool` | native_factory_declared_requires_full_audit | 0 | 0 | 0 | 8 |
| `img_tracking` | `chisurf.plugins.microscopy.img_tracking.gui.tool:ImgTrackingTool` | qt_or_other_gui_requires_port | 1 | 0 | 1 | 1 |
| `mle_common` | `none` | no_gui_entrypoint | 1 | 0 | 0 | 0 |
| `psf_determination` | `chisurf.plugins.microscopy.psf_determination.gui.tool:PsfDeterminationTool` | native_factory_declared_requires_full_audit | 2 | 2 | 3 | 4 |
| `region_mle` | `chisurf.plugins.microscopy.region_mle.gui.tool:RegionMleTool` | qt_or_other_gui_requires_port | 1 | 0 | 0 | 5 |
| `spot_finder` | `chisurf.plugins.microscopy.spot_finder.gui.tool:SpotFinderTool` | native_factory_declared_requires_full_audit | 1 | 2 | 2 | 6 |
| `breakout` | `chisurf.plugins.misc.games.breakout.breakout:Breakout` | native_factory_declared_requires_full_audit | 1 | 3 | 1 | 2 |
| `games` | `chisurf.plugins.misc.games.gui.tool:GamesWidget` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 1 |
| `minesweeper` | `chisurf.plugins.misc.games.minesweeper.gui.tool:MinesweeperWidget` | native_factory_declared_requires_full_audit | 1 | 2 | 1 | 4 |
| `number_quest` | `chisurf.plugins.misc.games.number_quest.gui.tool:NumberQuestWidget` | native_factory_declared_requires_full_audit | 1 | 1 | 1 | 4 |
| `pong` | `chisurf.plugins.misc.games.pong.pong:Pong` | native_factory_declared_requires_full_audit | 1 | 2 | 1 | 3 |
| `tetris` | `chisurf.plugins.misc.games.tetris.tetris:Tetris` | qt_or_other_gui_requires_port | 0 | 0 | 0 | 0 |
| `fps_json_editor` | `chisurf.plugins.modelling.fps_json_editor.gui.tool:FpsJsonEditorTool` | qt_or_other_gui_requires_port | 6 | 0 | 4 | 3 |
| `fret_docking` | `chisurf.plugins.modelling.fret.gui.dock_tool:FretDockingTool` | qt_or_other_gui_requires_port | 3 | 0 | 1 | 17 |
| `hydropro` | `chisurf.plugins.modelling.hydropro.gui.tool:HydroProTool` | qt_or_other_gui_requires_port | 3 | 0 | 0 | 1 |
| `proteinmc` | `none` | no_gui_entrypoint | 0 | 0 | 0 | 1 |
| `structure_tools` | `chisurf.plugins.modelling.structure_tools.gui.tool:StructureToolsTool` | qt_or_other_gui_requires_port | 1 | 0 | 0 | 0 |
| `ndxplorer` | `chisurf.plugins.ndxplorer.window:build_ndxplorer_window` | native_factory_declared_requires_full_audit | 7 | 0 | 1 | 13 |
| `pch` | `chisurf.plugins.pch.gui.tool:PCHApp` | qt_or_other_gui_requires_port | 1 | 0 | 1 | 5 |
| `quenching_estimator` | `chisurf.plugins.quenching_estimator.gui.tool:QuEstTool` | qt_or_other_gui_requires_port | 0 | 0 | 0 | 2 |
| `spectra_downloader` | `chisurf.plugins.spectra_downloader.gui.tool:SpectraTool` | native_factory_declared_requires_full_audit | 5 | 3 | 2 | 7 |
| `traj_fret` | `chisurf.plugins.traj.fret_trajectory.gui:Structure2Transfer` | qt_or_other_gui_requires_port | 2 | 0 | 1 | 2 |
| `traj_energy_calculator` | `chisurf.plugins.traj.potential_energy.widget:PotentialEnergyWidget` | native_factory_declared_requires_full_audit | 3 | 0 | 1 | 2 |
| `traj_align` | `chisurf.plugins.traj.traj_align.widget:AlignTrajectoryWidget` | native_factory_declared_requires_full_audit | 3 | 0 | 1 | 2 |
| `traj_convert` | `chisurf.plugins.traj.traj_convert.widget:MDConverter` | native_factory_declared_requires_full_audit | 3 | 0 | 1 | 2 |
| `traj_energy` | `chisurf.plugins.traj.potential_energy.widget:PotentialEnergyWidget` | qt_or_other_gui_requires_port | 0 | 0 | 0 | 0 |
| `traj_join` | `chisurf.plugins.traj.traj_join.widget:JoinTrajectoriesWidget` | native_factory_declared_requires_full_audit | 2 | 0 | 1 | 2 |
| `traj_remove_clashes` | `chisurf.plugins.traj.traj_remove_clashes.widget:RemoveClashedFrames` | native_factory_declared_requires_full_audit | 3 | 0 | 1 | 2 |
| `traj_rotate_translate` | `chisurf.plugins.traj.traj_rotate_translate.widget:RotateTranslateTrajectoryWidget` | native_factory_declared_requires_full_audit | 3 | 0 | 1 | 2 |
| `traj_save_topology` | `chisurf.plugins.traj.traj_save_topology.widget:SaveTopology` | native_factory_declared_requires_full_audit | 3 | 0 | 1 | 2 |
| `traj_tools` | `chisurf.plugins.traj.traj_tools.gui.tool:TrajectoryToolsTool` | qt_or_other_gui_requires_port | 1 | 0 | 0 | 1 |
| `tttr_audifier` | `chisurf.plugins.tttr.audifier.gui.tool:TTTRAudifierWidget` | native_factory_declared_requires_full_audit | 4 | 0 | 1 | 1 |
| `filetools` | `chisurf.plugins.tttr.filetools.gui.tool:FileToolsTool` | native_factory_declared_requires_full_audit | 0 | 0 | 0 | 1 |
| `intensity_trace` | `script: __init__.py` | legacy_script_requires_gui_audit | 1 | 0 | 1 | 0 |
| `microtime_histogram` | `chisurf.plugins.tttr.microtime_histogram.wizard:MicrotimeHistogram` | native_factory_declared_requires_full_audit | 2 | 0 | 0 | 9 |
| `photon_table` | `chisurf.plugins.tttr.photon_table.gui.tool:PhotonTableTool` | native_factory_declared_requires_full_audit | 1 | 3 | 2 | 1 |
| `ptu_alex_creator` | `chisurf.plugins.tttr.ptu_alex_creator.gui.tool:AlexPTUCreator` | native_factory_declared_requires_full_audit | 2 | 0 | 1 | 2 |
| `trace_browser` | `chisurf.plugins.tttr.trace_browser.gui.tool:TraceBrowserTool` | qt_or_other_gui_requires_port | 3 | 0 | 2 | 4 |
| `tttr_correlate` | `script: __init__.py` | legacy_script_requires_gui_audit | 0 | 0 | 0 | 2 |
| `tttr_count_rate_analysis` | `chisurf.plugins.tttr.tttr_count_rate_analysis.gui.tool:CountRateAnalyzer` | native_factory_declared_requires_full_audit | 2 | 2 | 2 | 3 |
| `tttr_header_edit` | `script: __init__.py` | native_factory_declared_requires_full_audit | 2 | 2 | 2 | 3 |
| `tttr_histogram` | `script: __init__.py` | legacy_script_requires_gui_audit | 0 | 0 | 0 | 3 |
| `tttr_image_browser` | `chisurf.plugins.tttr.tttr_image_browser.gui.tool:TTTRImageBrowserTool` | native_factory_declared_requires_full_audit | 3 | 0 | 1 | 5 |
| `tttr_lut_tools` | `chisurf.plugins.tttr.tttr_lut_tools.gui.tool:TTRLutToolsWidget` | native_factory_declared_requires_full_audit | 4 | 0 | 2 | 6 |
| `microtime_shifter` | `chisurf.plugins.tttr.tttr_microtime_shifter.gui.tool:MicrotimeShifterTool` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 7 |
| `tttr_splitter` | `script: __init__.py` | native_factory_declared_requires_full_audit | 2 | 3 | 3 | 2 |
| `tttr_time_windows` | `chisurf.plugins.tttr.tttr_time_windows.gui.tool:TTTRTimeWindowTool` | native_factory_declared_requires_full_audit | 2 | 3 | 2 | 3 |
| `tttr_toolbox` | `chisurf.plugins.tttr.tttr_toolbox.gui.tool:TttrToolboxTool` | native_factory_declared_requires_full_audit | 0 | 0 | 0 | 1 |
| `vv_vh_anisotropy` | `chisurf.plugins.vv_vh_anisotropy:VvVhAnisotropyCalculator` | native_factory_declared_requires_full_audit | 1 | 2 | 1 | 2 |
| `vv_vh_g_factor` | `chisurf.plugins.vv_vh_g_factor.gui.tool:VvVhGFactorCalculator` | native_factory_declared_requires_full_audit | 1 | 0 | 0 | 7 |

Excluded manifests:
- `chisurf/plugins/chimol/test/renders/gl_baseline/manifest.json`
- `chisurf/plugins/cookiecutter-chisurf-plugin/{{cookiecutter.plugin_name}}/manifest.json`

## Root-note queue disposition — verified 2026-10-07

This continuation record folds `AGY_BRIEF.md` and `CODEX_TASK.md` from
2026-10-03; it does not replace the historical inventory above or claim that a
factory declaration is acceptance. Workstream order and ownership now come
from [the release programme](../prds/prd-154.md), and acceptance from
[the documentation standard](documentation-standard.md).

The old four-item preview snapshot is superseded: the live
[preview file](../../chisurf/core/plugin/emtk_preview.json) contains only
`code_editor`. The previously described missing-port queue has moved: the
current manifests declare native factories for `burst_h2mm`,
`burst_mle_analysis`, `hydropro`, `mfd_prepare`, `burst_ebfret`, `alex_suite`,
`fret_docking`, `fps_json_editor`, `burst_analysis`, `burst_selection`, `acq`,
`mmfdb_admin`, `batch_analysis`, `wizards` and `traj_tools`. Reports exist under
`emtk-ports/<id>/REPORT.md` for these except `burst_selection`; declaration,
report existence and removal from the preview list are three different facts.

1. Re-audit `code_editor` against its current [report](emtk-ports/code_editor/REPORT.md)
   and real controls before changing its gate entry. The old rejection recorded
   29 missing Qt controls and editor input gaps; that is historical evidence to
   compare against, not a current measurement or permission to ungate it.
2. `quenching_estimator` remains Qt-only in its
   [manifest](../../chisurf/plugins/quenching_estimator/manifest.json), despite
   [an existing report](emtk-ports/quenching_estimator/REPORT.md). Its factory can
   construct while its layout and external-viewer imports remain broken; see
   [the current programme evidence](../validation/release-readiness-w7.md).
3. For already declared factories, fill any missing populated screenshots,
   click coverage, control inventory or tour evidence before assuming a port is
   accepted. Re-derive the queue from manifests plus the preview file and reports;
   do not reuse the old 123/109 totals or the dead-session priority list.

The `fret_docking` owner is
[the modelling/fret plugin](../../chisurf/plugins/modelling/fret/manifest.json),
not the obsolete `modelling/fret/fret_docking` path. The old brief's prohibition
on touching sibling emtk or posting a shared-board claim was specific to that
session's sandbox/supervision and is superseded by current repository rules.
Historical commit ids remain provenance in the original notes, not unverified
instructions to repeat their implementation.

The historical strict-xfail worklist named tour-card buttons over a data table,
Ctrl+A in table filters/cell editors, and Enter on an emptied text field. Treat
these as scenarios to re-check against current emtk input/guide tests, not as
newly established defects; the old table-resize/reorder/multiselect, image-export
and docking-overflow gap list is likewise a capability audit before acceptance.
