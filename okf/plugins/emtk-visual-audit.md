---
type: Plugin Note
title: Independent native plugin visual audit
description: Historical native and Qt startup visual verdicts, their archived local evidence, and the limits on functional or release acceptance.
tags: [plugins, emtk, visual-audit, historical-evidence]
timestamp: '2026-10-10T00:00:00Z'
---

# Independent native plugin visual audit

## Historical evidence availability

The 52 image references in this page originally pointed to local, Git-ignored
files. All 52 were present when preserved; none was tracked as a published image.
Their unchanged bytes, adjacent capture metadata, the rich-document fixture and
copies of the structured audit records are now members of the
[concurrent OKF source evidence archive](../validation/release-readiness-w0a/concurrent-okf-source-evidence.zip).
Member names below are code references inside that archive, not image URLs.
`visual-audit/asset-manifest.json` records each original local path, ignore status,
size and SHA256. Extract the archive to inspect the referenced members.

These are historical captures. Packaging them does not rerun a plugin, revise a
score, establish a currently loaded workflow or renew any release acceptance.
The original scores, dates, scope restrictions and outstanding checks below are
retained unchanged. The structured JSON files also retain their original local
paths as provenance; the archive manifest maps those paths to preserved members.

### Re-derive evidence when its owner resumes the audit

`visual-audit/reproduction.json` lists current native factories from tracked
manifests and per-plugin commands, including their source revision. These
commands were read from the tracked tools, not executed for this repair.
Use disposable settings/database directories and a new output directory.

- For a current **CPU startup** capture, use the tracked
  [native factory checker](../../build_tools/dev_utils/emtk_migration/check_native.py)
  with `--factory MODULE:CALLABLE --screenshots /private/tmp/plugin-current-cpu.png`.
  Its renderer is `PilPainter`; it does not reproduce historical GPU evidence.
- For a genuine historical **Qt reference**, use the tracked
  [Qt reference capture tool](../../build_tools/dev_utils/emtk_migration/capture_qt_references.py)
  with `--plugins PLUGIN_ID --jobs 1 --tab-pages --output /private/tmp/plugin-qt-reference`
  under `QT_QPA_PLATFORM=offscreen pixi run -e test python`. The output records
  the selected source revision; it need not match the revision originally scored.
- The help fixture is preserved at archive member
  `visual-audit/assets/help-rich-document/fixture/feature_reference.md`.
  The Qt tool accepts it through `--document` with `--width 1280 --height 900`.
  The tracked [populated help capture](emtk-ports/help/scripts/capture_populated.py)
  uses a different page and viewport; it is a starting point, not an equivalent
  reproduction of the archived CPU v3/v4 images.

The original GPU driver command/environment and exact CPU v3/v4 capture driver
were not preserved in this record. A matched replacement requires a separately
reviewed capture using the archived fixture and state. No GPU or current
functional result is inferred from the available CPU/Qt recipes.

## Latest GPU re-audit (version2)

[Structured refresh](emtk-visual-audit-refresh.json) preserves31fresh startup GPU verdicts and11additional scoped scenarios. All images are frozen/versioned with SHA256; prior verdicts remain below as history. Twenty startup layouts score90+, but no full-function/tooltip/full-port flag follows from this review.

Exact rich-document GPU fixture independently scores93/pass. Structured ChannelDefinition replaces the prior Background/IRF JSON-only gap; six section captures are CPU PilPainter. CountRate defaultGPU predates its shared-editor fix; the newer populated CPU/narrow images score91 and supersede that particular source gap. Those CPU frames are not GPU proof.

Kappa2 current numbers match seeded current Qt-adapter/native tests reported by owner; archived Qt d52ac24 predates unbiased-moment fixes, so historical0.7447 is not a current numeric golden. Remaining notes include cropped plot tags/optical captions, loaded FCS-filter GPU proof, and actual workflows/hover/persistence. Original Optical Setup is LightPathEasyDialog; graph editing is a separate advanced scope.

| Plugin | FreshGPU score | Verdict | First finding |
| --- | ---: | --- | --- |
| burst_background | 91 | pass | The raw JSON-only detector block has been replaced by a separate structured Channel Definition dock. |
| burst_irf_bg | 91 | pass | Structured Channel Definition and folder input are now represented. |
| burst_bva | 88 | revise | Channel Definitions is now an explicit tab. |
| burst_fcs_correlator | 75 | revise | Named channel-pair selection is exposed as raw JSON rather than an editor. |
| burst_2cde | 90 | pass | Native layout switches from stacked form/plot to a sidebar and large plot; the documented fields remain visible. |
| burst_gs | 88 | revise | Native startup places many parameters in one dense sidebar; file list and derived state/rate views are not populated. |
| burst_browser | 91 | pass | Detector and Histogram column labels now identify the empty dropdowns. |
| burst_fusion | 88 | revise | Estimate options and file type are now visible. |
| calculators | 82 | revise | The embedded FRET form retains a very tall empty parameter pane while plots dominate the right. |
| fret_calculator | 90 | pass | Native default HeteroFRET parameters and two distribution plots are visible; HomoFRET is not opened. |
| phasor_calculator | 91 | pass | Default geometry and reference-lifetime table remain readable. |
| kappa2_dist | 90 | pass | Computed statistics are now visible. |
| psf_calculator | 90 | pass | Native and Qt startup states both leave the volume view unpopulated. |
| rics_precision | 91 | pass | Default settings and prediction table/plot categories remain recognizable. |
| fcs_saturation | 88 | revise | Main field labels are now above controls and fitting-state/bounds editors are represented. |
| fcs_calculator | 87 | revise | Numeric parameter labels now sit above their fields. |
| fret_line | 91 | pass | Sweep/Add FRET line/CSV/overlay controls are now visible in a dedicated pane. |
| fcs_filter_calculator | 82 | revise | Fresh GPU shows an empty/disabled startup state instead of the prior populated reconstruction. |
| fcs_merger | 92 | pass | Input/output paths now have clear labels and placeholders. |
| code_editor | 84 | revise | Document/dock close icons remain present. |
| help | 93 | pass | Address entry and neutral virtual-page status are restored. |
| f_test | 90 | pass | Native two-panel layout preserves both nested-fit and chi-square-limit forms. |
| tttr_splitter | 92 | pass | Main input/output/options/batch controls remain visible and clearly grouped. |
| tttr_time_windows | 91 | pass | Input, settings, intensity preview and log panes are clearly separated. |
| photon_table | 0 | fail | No genuine original Qt reference is available in the captured history, so visual parity cannot be scored. |
| irf_estimator | 91 | pass | Initial IRF settings and output panes are readable; no decay/IRF/result numbers are loaded. |
| synthetic_decay | 91 | pass | Lifetime/rotation spectra and generator controls are represented; decay/anisotropy outputs are empty. |
| psf_determination | 90 | pass | Bead image/profile/results panes and optical/ROI/detection controls are present; no stack or fitted bead is shown. |
| spot_finder | 90 | pass | Workflow/detector/picking/region sections are represented; image, regions and run table are empty. |
| microtime_shifter | 91 | pass | File/shift/batch/database controls are represented; per-channel shifts require loaded photons. |
| tttr_count_rate_analysis | 68 | revise | Saved-setup chooser is represented but Edit setup currently opens raw JSON/in-memory setup edits. |

This reviews the 25 initial 1200 × 800 GPU screenshots in `/private/tmp/chisurf-native-gpu` against genuine Qt references and current source. It does **not** certify all functionality, all tooltips, or complete plugin conversion. Only 24 have an available Qt baseline. A score of 90 or higher passes the observed startup layout only.

Several controllers/forms/toolkit components changed after capture. Stale screenshots must be regenerated before closing their issues. Source declarations show intended controls but cannot prove click, hover, cancellation, persistence or scientific-output behavior. Qt reference captures can have different initial data and asynchronous settling time.

The structured record is [emtk-visual-audit.json](emtk-visual-audit.json). Per-plugin independent verdicts are retained in `.omx/state/<plugin>/ralph-progress.json` without replacing implementation owners' verdicts.

| Plugin | Score | Verdict | Primary startup finding |
| --- | ---: | --- | --- |
| burst_background | 58 | revise | The native detector area is a raw JSON editor; the Qt Channel Definition tab has structured setup/calibration/reader/PIE/LUT/detector controls. |
| burst_irf_bg | 60 | revise | The original full Channel Definition tab is reduced to detector JSON in the native startup view. |
| burst_bva | 82 | revise | Setup and donor/acceptor assignment fields visible in Qt are hidden behind the native Channel Definitions action. |
| burst_fcs_correlator | 75 | revise | Named channel-pair selection is exposed as raw JSON rather than an editor. |
| burst_2cde | 90 | pass | Native layout switches from stacked form/plot to a sidebar and large plot; the documented fields remain visible. |
| burst_gs | 88 | revise | Native startup places many parameters in one dense sidebar; file list and derived state/rate views are not populated. |
| burst_browser | 82 | revise | Detector and histogram-column dropdowns are unlabeled/blank in the empty startup view. |
| burst_fusion | 82 | revise | The startup summary header abbreviates selection and lacks a visible units column compared with Qt. |
| calculators | 82 | revise | The embedded FRET form retains a very tall empty parameter pane while plots dominate the right. |
| fret_calculator | 90 | pass | Native default HeteroFRET parameters and two distribution plots are visible; HomoFRET is not opened. |
| phasor_calculator | 91 | pass | Default geometry and reference-lifetime table remain readable. |
| kappa2_dist | 78 | revise | Orientation-statistics values are invisible in the native image while Qt displays computed numbers. |
| psf_calculator | 90 | pass | Native and Qt startup states both leave the volume view unpopulated. |
| rics_precision | 91 | pass | Default settings and prediction table/plot categories remain recognizable. |
| fcs_saturation | 64 | revise | Many right-hand field labels clip at the native sidebar edge. |
| fcs_calculator | 78 | revise | Almost full-width fields push labels to the right edge; Fixed constraint is clipped. |
| fret_line | 62 | revise | Long per-parameter value/fixed/bounds editors push Add FRET line/Save CSV/Push to ndX below the startup viewport. |
| fcs_filter_calculator | 64 | revise | Reconstruction log-count scale spans roughly 240 decades, flattening observed and reconstructed curves. |
| fcs_merger | 80 | revise | Two empty text fields lack visible input/output path labels in the old native image. |
| code_editor | 84 | revise | Python Console sidebar tab title clips behind the dock close area. |
| help | 73 | revise | Native toolbar lacks Qt's visible Address input for direct document/source/citation navigation. |
| f_test | 90 | pass | Native two-panel layout preserves both nested-fit and chi-square-limit forms. |
| tttr_splitter | 92 | pass | Main input/output/options/batch controls remain visible and clearly grouped. |
| tttr_time_windows | 91 | pass | Input, settings, intensity preview and log panes are clearly separated. |
| photon_table | 0 | fail | No genuine original Qt reference is available in the captured history, so visual parity cannot be scored. |

## burst_background

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/burst_background.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/burst__burst_background.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

High-priority Channel Definition coverage gap confirmed in shared controller source.

- The native detector area is a raw JSON editor; the Qt Channel Definition tab has structured setup/calibration/reader/PIE/LUT/detector controls.
- The native sidebar allocates most upper space to implementation-format JSON instead of measurement setup fields.

Next visual checks:

- Restore the complete shared native Channel Definition editor, including setup CRUD, calibration, timing overrides, PIE/LUT and optical setup.
- Use named detector rows and keep JSON as an optional advanced import/export view.

Still unverified:

- Named setup/calibration/LUT round trips and reader unit overrides.
- Folder add, populated per-file removal, cancellation and populated fit/rate/results views.


## burst_irf_bg

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/burst_irf_bg.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/burst__burst_irf_bg.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Initial controls retain burst-search parameters, but full measurement setup parity is not established.

- The original full Channel Definition tab is reduced to detector JSON in the native startup view.
- The original Files/Folder/Database/Remove workflow is not fully demonstrated by native Open/Clear controls.

Next visual checks:

- Share a complete native Channel Definition editor with Background; preserve timing, PIE/LUT, calibration and detector metadata.
- Capture loaded IRF/baseline/results states and demonstrate folder/add/remove interactions.

Still unverified:

- Channel Definition feature parity.
- Non-burst selection, baseline/IRF plotting, MLE handoff/export and cancel.


## burst_bva

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/burst_bva.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/burst__burst_bva.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Core BVA inputs and plot category remain recognizable; setup and data-driven interactions remain unverified.

- Setup and donor/acceptor assignment fields visible in Qt are hidden behind the native Channel Definitions action.
- Native parameter rows are tighter and smaller; the default plot contains an interactive region not demonstrated against loaded data.

Next visual checks:

- Verify the Channel Definitions window exposes setup and pair assignment before marking parity.
- Capture populated BVA with selected detectors and assert plot bounds/static-line/region behavior.

Still unverified:

- Detector setup/pair selection.
- Run/restart/stop, save plot/defaults, automatic update and loaded BVA outputs.


## burst_fcs_correlator

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/burst_fcs_correlator.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/burst__burst_fcs_correlator.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

The correlation and diffusion panes are present; configuration and populated selection workflows need evidence.

- Named channel-pair selection is exposed as raw JSON rather than an editor.
- Qt Select All/None and populated input/curve lists are not demonstrated by the startup capture.

Next visual checks:

- Provide structured channel-pair fields or a clearly scoped advanced JSON editor plus normal editing UI.
- Capture multiple files/pairs and fit modes, proving selection and export rather than only empty plots.

Still unverified:

- Pairs/microtime gate editing and round trips.
- All/None/remove, simple/MaxEnt fitting, diffusion distribution and exported curves.


## burst_2cde

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/burst_2cde.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/burst__burst_2cde.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Startup visual controls match the scientific purpose without obvious clipping; no behavioral acceptance follows from this score.

- Native layout switches from stacked form/plot to a sidebar and large plot; the documented fields remain visible.
- The startup empty plot cannot demonstrate either FRET-2CDE or ALEX-2CDE computed state.

Next visual checks:

- Retain this readable field hierarchy and verify variant/kernel changes using matched loaded data.
- Add hover screenshots/tests for units, routing channels, file type and run controls.

Still unverified:

- FRET/ALEX variants, kernels and physical window units.
- Folder selection, run/restart/cancel and populated chart/export behavior.


## burst_gs

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/burst_gs.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/burst__burst_gs.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Source contains the additional derived tables, so their absence in the startup image is an evidence gap rather than a claimed missing implementation.

- Native startup places many parameters in one dense sidebar; file list and derived state/rate views are not populated.
- Qt separate Rates/States/State populations/Transition time views are not demonstrated by the default native report/plot.

Next visual checks:

- Capture simulation and real-fit results showing rate matrix, populations, state efficiencies and transition profile.
- Group secondary parameters and keep fitting actions visible at smaller sizes.

Still unverified:

- Simulation and real TTTR/burst fitting.
- Rate/state/population/transition outputs, CSV, cancellation, H2MM cross-check and timing units.


## burst_browser

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/burst_browser.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/burst__burst_browser.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

The richer layout is recognizable but empty selection widgets need clearer meaning; source is newer than the screenshot.

- Detector and histogram-column dropdowns are unlabeled/blank in the empty startup view.
- Native three-column docking leaves narrow table/histogram panes; loaded selection/gates are not shown.

Next visual checks:

- Add visible Detector and Histogram column labels and informative empty placeholders.
- Capture populated table, row-selection histogram, E/S/size gates and context/clipboard/export workflows.

Still unverified:

- Loaded table selection, detector-specific gate ranges and histogram updates.
- Gate/selected export, folder/file/database inputs and cancellation.


## burst_fusion

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/burst_fusion.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/burst__burst_fusion.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

The plot suite is represented; source changed after capture and populated results still need comparison.

- The startup summary header abbreviates selection and lacks a visible units column compared with Qt.
- Folder placeholder text clips in the controls pane; the five empty plots do not prove fusion diagnostics.

Next visual checks:

- Preserve quantity/selection/fused/unit meanings in a readable summary table.
- Capture a fused example showing before/after plots, probabilities, report export and parameter effects.

Still unverified:

- Fuse versus estimate, settings/load/export and input data handling.
- Summary units, populated five diagnostic plots, selection lineage and cancellation.


## calculators

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/calculators.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/calculator__hub.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

The navigation category is preserved; one selected page cannot verify the complete hub.

- The embedded FRET form retains a very tall empty parameter pane while plots dominate the right.
- The initial hub image shows only the FRET page, not all calculator pages or nested popup/dock layouts.

Next visual checks:

- Apply shared label-aware forms consistently inside hub content.
- Capture each hub page and verify embedded controls/popups/close lifecycles stay within the hub viewport.

Still unverified:

- Every hub page and nested tooltip/popup/dock behavior.
- Page switching, computation, cancellation and resource cleanup.


## fret_calculator

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/fret_calculator.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/calculator__fret_calculator.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

The startup calculator is visually coherent; hidden mode and conversion correctness remain outside the screenshot claim.

- Native default HeteroFRET parameters and two distribution plots are visible; HomoFRET is not opened.
- The new layout differs from Qt but does not visibly clip the main parameter units.

Next visual checks:

- Capture HomoFRET and each linked conversion input direction.
- Verify distribution/chi toggles and tooltip explanations against backend golden values.

Still unverified:

- HeteroFRET distance/efficiency/lifetime/rate conversion directions.
- HomoFRET exchange/backmap, both distributions and hover behavior.


## phasor_calculator

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/phasor_calculator.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/calculator__phasor_calculator.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Default semicircle/lifetime geometry is clear and the scientific category matches; interactive geometry remains unverified.

- Default geometry and reference-lifetime table remain readable.
- Collapsed two-component/mixing/cursor sections are not compared in this image.

Next visual checks:

- Capture two-component, mixing-region and cursor states with all reference geometry toggles.
- Verify frequency/harmonic/CSV lifetime controls and scientific coordinate readouts.

Still unverified:

- Frequency/harmonic changes and reference lifetime parsing.
- Polar grid, FRET trajectory, mixture line/region and cursor readouts.


## kappa2_dist

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/kappa2_dist.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/calculator__kappa2_dist.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

A plot is visible but its numerical summary is unreadable; owner diagnosed toolkit normalized-alpha rendering, not missing calculation data.

- Orientation-statistics values are invisible in the native image while Qt displays computed numbers.
- The true-kappa annotation overlaps lower-axis tick labeling.

Next visual checks:

- Fix result text visibility and recapture all numeric statistics.
- Offset the editable annotation from tick labels and verify all model modes/known-delta/save interactions.

Still unverified:

- WIC, diffusion and isotropic modes, angular/bin controls and bounds.
- Result numeric visibility, true-kappa drag/tooltip, delta-known and saved distributions.


## psf_calculator

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/psf_calculator.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/calculator__psf_calculator.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

The initial parameter layout is usable; no volume-rendering or compute correctness claim is supported by this frame.

- Native and Qt startup states both leave the volume view unpopulated.
- Native says Not computed yet and Computing, so this image is an intermediate state rather than completed optical output.

Next visual checks:

- Capture completed volume and each orthogonal slice before accepting rendering parity.
- Verify optical/polarization/display controls, cancellation and NPY/TIFF exports on actual computed data.

Still unverified:

- Scalar/vector optical modes, polarization, quality and spatial sampling.
- 3D volume, XY/XZ/YZ slice interaction, threshold/gamma/colormap and exports.


## rics_precision

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/rics_precision.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/calculator__rics_precision.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Default settings are readable; computed precision and secondary estimator modes remain unverified.

- Default settings and prediction table/plot categories remain recognizable.
- Estimator settings are collapsed and Predict has not populated numbers or curves.

Next visual checks:

- Capture expanded estimator options and a completed dwell sweep.
- Compare numeric prediction table and CSV with the same Qt/backend settings.

Still unverified:

- Sample/optics/scan/estimator choices and physical units.
- Predicted dwell sweep, line/frame times, numeric table and CSV.


## fcs_saturation

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/fcs_saturation.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/calculator__fcs_saturation_calc.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Parameter constraints and labels need correction; owner reports source fixes, but this GPU frame predates them.

- Many right-hand field labels clip at the native sidebar edge.
- Native state brightness/optics value fields omit Qt's visible Fixed/Bounds-enabled/Lo/Hi editing affordances in this captured version.
- State diagram is shown while the prediction area is empty compared with the computed Qt reference.

Next visual checks:

- Use label-aware forms and preserve complete parameter constraint editors.
- Capture fully computed FCS/residual/profile/power/diffusion states, including normalization and fit overlays.

Still unverified:

- Arbitrary schemes/state counts, directed rates, brightness and fixed/bounds editing.
- FCS/residual/volume/power/diffusion views, toggles and scheme/session persistence.


## fcs_calculator

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/fcs_calculator.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/fcs__fcs_calculator.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Core scientific values are present but label layout and reference/default handling need clearer evidence.

- Almost full-width fields push labels to the right edge; Fixed constraint is clipped.
- Reference dye defaults blank and shape differs from Qt, requiring an intentional default-state explanation.

Next visual checks:

- Put labels above/beside sensibly sized fields and make units consistently legible.
- Capture all fixed constraints, reference dyes, temperature scaling and shapes, and explain intended default differences.

Still unverified:

- Fix D/r_h/Veff and coupled occupancy/concentration.
- Water viscosity, reference scaling, sphere/ellipsoid/cylinder and JSON round trips.


## fret_line

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/fret_line.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/fret_line.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

The initial layout hides the tool's primary action; owner reports a separate editor dock and compact constraint details in newer source.

- Long per-parameter value/fixed/bounds editors push Add FRET line/Save CSV/Push to ndX below the startup viewport.
- Sweep and computed-line collection are not discoverable in the initial native pane compared with Qt tabs and fixed footer.

Next visual checks:

- Separate or compact the parameter editor and pin primary sweep/export/overlay actions.
- Capture sweep and line collection controls with multiple computed lines and real backend outputs.

Still unverified:

- Component/subcomponent models, canonical values/fixed/bounds, live donor reference and sweep targets.
- Add/remove/show/hide/clear lines, CSV and ndX overlays.


## fcs_filter_calculator

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/fcs_filter_calculator.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/fcs__fcs_filter_calculator.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Observed range is unusable in the old GPU frame; source/CPU fix is reported but a fresh GPU/matched-data comparison is needed.

- Reconstruction log-count scale spans roughly 240 decades, flattening observed and reconstructed curves.
- The startup screenshot is a synthetic loaded project whereas the original Qt reference is empty, so a direct data-result comparison is unmatched.

Next visual checks:

- Use useful count limits and recapture the same project in Qt and native renderers.
- Verify detector setup, measured patterns, component removal, auto-fit/instrument modes, unmix and project/export paths.

Still unverified:

- Matching loaded-project reconstruction/filter/residual outputs.
- All source types, detector/polarized/global modes, fit range, auto-fit, instrument settings, unmix and persistence.


## fcs_merger

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/fcs_merger.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/fcs__fcs_merger.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Empty plotting hierarchy is clear; field labels and loaded selection/results need renewed evidence after newer source changes.

- Two empty text fields lack visible input/output path labels in the old native image.
- The original Qt Use-selection table is not populated, so selecting curves and saving the merged result are unverified.

Next visual checks:

- Show Folder and Output path labels/placeholders explicitly.
- Capture multiple curves, use toggles, selected/merged diagnostics, save-as and host integration.

Still unverified:

- File/folder load errors, curve selection and interpolation/weighting/uncertainty rules.
- Merged outputs, save/save-as/Add to ChiSurf, clear/remove and hover behavior.


## code_editor

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/code_editor.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/core__code_editor.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

The basic editor is visually usable and close icons exist; the specific earlier regressions require interaction evidence.

- Python Console sidebar tab title clips behind the dock close area.
- The active main.py tab has a close icon, but no context menu, multiple-document or modified-close state is shown.

Next visual checks:

- Use overflow handling or a tab menu so long sidebar titles remain readable.
- Capture right-click menus, active new/opened files, dirty Save/Discard/Cancel and notebook/diagnostic states.

Still unverified:

- File dock/document tab/dock-header context menus and all close/reopen actions.
- Open/new activation, save-as/cancel, runtime modes/stop, Ruff/LSP/notebook and actual hover tooltips.


## help

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/help.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/core__help.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Default page comparison exposes missing navigation/provenance affordances; core owner is implementing fixes and a rich fixture is pending.

- Native toolbar lacks Qt's visible Address input for direct document/source/citation navigation.
- Welcome is marked Reviewed although it is a virtual page with no current file/review record.
- Welcome-only rendering does not demonstrate rich equations/figures/tables or original review write controls.

Next visual checks:

- Restore direct address navigation and explicit human/AI review operations; do not mark virtual pages reviewed.
- Compare a matched loaded rich document with anchors, figures, tables, math and citations, including actual link/hover interactions.

Still unverified:

- Rich document layout, address/source/cite links, internal/external anchors and navigation history.
- Search, source save/cancel, review persistence, Ask Docs/provider/error states and tooltips.


## f_test

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/f_test.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/core__f_test.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Both initial statistical forms are legible; visual pass is limited to this default frame.

- Native two-panel layout preserves both nested-fit and chi-square-limit forms.
- Default screenshot has no live fit to demonstrate the new fit-selection integration.

Next visual checks:

- Retain readable form labels and capture loading each model from live fits.
- Verify valid/invalid inputs, degrees of freedom, linked confidence/output behavior and hover descriptions.

Still unverified:

- Both statistical calculations and invalid/boundary inputs.
- Live-fit refresh/load and tooltip behavior.


## tttr_splitter

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/tttr_splitter.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/tttr__tttr_splitter.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Default layout improves visibility of batch options; successful conversion is not proven by its presence.

- Main input/output/options/batch controls remain visible and clearly grouped.
- Batch queue, progress, cancellation and output files are absent from the startup image.

Next visual checks:

- Capture a queued batch and actual conversion/split progress with the same Qt options.
- Verify all formats, units, microtime binning/reset/keep-original, folder/database inputs and stop semantics.

Still unverified:

- Single and batch splitting/conversion with real TTTR data.
- Chunk/file cancellation, output location/format/content, queue remove/clear and tooltips.


## tttr_time_windows

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/tttr_time_windows.png`). Qt reference: initial frame (historical archive member `visual-audit/assets/tttr__tttr_time_windows.png`). The JSON record lists all captured Qt tab pages and source/control inventories.

Default control hierarchy is coherent; trace and generated-window correctness remain unverified.

- Input, settings, intensity preview and log panes are clearly separated.
- Startup has no selected file or populated trace/window boundaries.

Next visual checks:

- Capture a real trace with edited window duration and processed log/output.
- Exercise Files/Folder/Database/Remove, output chooser, progress/cancel and physical time units.

Still unverified:

- Supported formats/compression, selected-file previews and duration changes.
- Window BID output, per-file counts, cancellation/partial-output semantics and tooltips.


## photon_table

Native: GPU frame (historical archive member `visual-audit/assets/native-audit-startup-gpu/photon_table.png`). Qt reference: unavailable. The JSON record lists all captured Qt tab pages and source/control inventories.

Comparison is blocked by unavailable Qt baseline; score 0 is not a judgment of native visual quality.

- No genuine original Qt reference is available in the captured history, so visual parity cannot be scored.
- Native screenshot is an empty table; paging/channel/copy behavior is not demonstrated.

Next visual checks:

- Establish an original/approved baseline or explicitly document that this plugin began as native.
- Capture populated photons and test time units, channel filtering, paging and copy-visible behavior.

Still unverified:

- Reference availability.
- Real TTTR table contents, paging/filtering/clipboard, asynchronous load cancellation and hover behavior.


## Help matched rich-document scenario

A deterministic 1280 × 900 fixture compares display/inline math, table, figure, note and anchor-link content. Qt reference (historical archive member `visual-audit/assets/help-rich-document/core__help.png`) and native CPU v3 (historical archive member `visual-audit/assets/help-rich-document/native-review-v3.png`) use the same source and top/read state. The native renderer is `emtk.testing.PixelPainter`, not GPU.

Score **88 / revise**: content renders correctly, but H1/H2 typography remains body-sized. The owner confirmed PixelPainter glyph size/advance omit `_font_scale`; GPU behavior is not inferred. Address entry and neutral review display were restored in this version. Recapture CPU after the toolkit fix and obtain a matched GPU frame. Links, tooltips, review persistence, source editing and all other rich directives remain unverified.

### Rich-document CPU correction verified

Native CPU v4 (historical archive member `visual-audit/assets/help-rich-document/native-review-v4.png`) independently scores **92 / pass for this fixture only**. The PixelPainter correction restores distinct H1/H2/body hierarchy without disturbing fraction/exponent, table, figure, note or link. The older88/revise record remains as before/after evidence. Matching GPU capture and functional/hover/review tests remain unverified.
