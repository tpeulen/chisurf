---
type: Plugin
title: ndX on emtk (the port off PyQt)
description: The ndXplorer emtk app (modules/ndxplorer/ndxplorer/app), which is replacing the Qt window. It runs on a desktop and in a browser, and parity is proven scenario by scenario from screenshots.
resource: modules/ndxplorer/ndxplorer/app/
tags: [plugins, ndxplorer, emtk, port, parity]
timestamp: '2026-09-23T00:00:00Z'
---

The owner decided that ndX moves off PyQt onto emtk. The new app (`ndxplorer/app/`)
lives beside the Qt window until it reaches parity, and then the Qt GUI is
deleted. The same app object runs in a native window, in a browser (Pyodide +
WebGPU through `emtk.web`) and in the headless capture. Parity is judged by
**control inventory** against the Qt baseline shots: `tools/parity/scenarios.json`,
`parity/qt/`, the checklist `tools/parity/features.md`, and
`python -m ndxplorer.app.capture -s <id>` for the emtk shots. The core
(`frame`, `model`, `view_model`, `menus`, `plots`, `capture`) draws the window.
Everything else is a feature module in `ndxplorer/app/features/` that
registers through `create(app) -> Feature` (hooks are documented in
`features/__init__.py`). The ndX concept itself is
[ndxplorer.md](ndxplorer.md).

## Where to pick this up

### core (window, main view, hooks, capture)

Re-measure with `python -m ndxplorer.app.capture -s open_mfd_folder -s axes_fdfa_tau
-s axes_log_norm_bins -s colour_log_contrast -s menu_file -s clear_plot -s startup_empty`
(arm64 env; every scenario runs in a scratch `$HOME`) and `pytest
ndxplorer/tests/test_app/test_emtk_app.py ndxplorer/tests/test_qt_free_logic.py`
(the core tests build `NdxApp(features=[])`). Compare each shot with `parity/qt/`
by control inventory; the ticks are in `tools/parity/features.md`.

1. **Parity status, 2026-09-23.** The main-view scenarios above are ticked:
   same default axes, stored axis settings (Fd/Fa log 0.1..500 on selection),
   counts 12237/12237, colour limits 1.00e+00 / 2.01e+02, bins and ranges as
   spin boxes, shortcuts Ctrl+O/Ctrl+I, drop to open, status line. The look is
   emtk's and ImPlot's default (user directive): no Qt palette, no proportional
   font; `theme.py` only maps x/y/z/gate to ImPlot's first colormap colours.
   Deliberate difference: `log #` re-derives vmin/vmax in log10 units; the Qt
   window keeps linear limits over a log image (its map washes out).
2. **Open, core:** the window title with the file name (`global`). The native
   and Tk hosts take a fixed title; a host API to retitle (`control.window_title`
   read each frame) has to go into emtk `native.py` / `tk_host.py`, which the HiDPI
   work was editing at the time.
3. **Check on a real Retina screen** after the emtk HiDPI fix (emtk `d7d1f23`
   and later): offscreen captures run at ratio 1 and hid glyphs drawn 2x too
   large and a window opened at ~986x605 instead of 1400x900. The view specs
   still use fixed pixel widths for bins (58 px) and buttons; re-check them
   for clipping at the real ratio.
4. **Browser boot not taken yet.** `ndxplorer.app.frame:make_app` is the factory
   for `python -m emtk.web.serve --app ...`; nothing under `ndxplorer/app` imports
   Qt (a test checks a fresh process) and the data layer imports without Qt
   (package `__init__`s are lazy), but tttrlib for Pyodide is still being built.
5. **Hooks** (`features/__init__.py`): actions/available/fields, menu_entries,
   custom_sections (`playback`, `draw_mask` in the core spec), tabs,
   draw_windows, draw_plot/plot_input, mask_terms, map_image, on_data_changed,
   on_z_select, animating, files_dropped, capture_ops/targets/actions; plus
   `NdxApp.open_menu` and `show_status`. Add a hook rather than editing a
   feature from the core.

Qt-free logic both GUIs call (moved, not copied): `core/gates.py`,
`core/histograms.py` (display_counts, colour_limits, auto_contrast_limits),
`plotting/colormap_lut.py` (pyqtgraph's map files read without pyqtgraph),
`settings/bundle.py`, `utils/axis_helpers.settings_for_axis`,
`DataSource.merge(warn=...)`. emtk gained on the way: view_form folds, fixed
widths, host-drawn custom sections, spin boxes (`style: "spin"` / `spin: true`),
combo-box choices, data_table editing (check boxes, cell edits, delete),
`FileDialog(mode="folder")`, `Texture(filter="nearest")`, windows with an opaque
background, edge tick labels kept inside the frame, labelled minor ticks on
short log axes, `Style.frame_border_size`, the Qt host honouring `animating()`.

### selection (gate table, context menus, pick population, z gate, draw mask, NaN/inf, weights)

Re-measure with `python -m ndxplorer.app.capture -s gate_rectangle -s gate_invert_disable
-s selection_table_menu -s canvas_context_menu -s pick_population -s z_axis_dynamic
-s z_add_selection -s draw_mask -s mask_nan_inf_off -s weights`, and run `pytest
ndxplorer/tests/test_app/test_selection.py ndxplorer/tests/test_qt_free_logic.py` plus
(Qt, offscreen) `ndxplorer/tests/test_ui/test_gate_table.py`.

1. **Parity status, 2026-09-23: all ten scenarios captured and ticked** in
   `tools/parity/features.md`. Counts match the Qt shots: weights, NaN/inf off
   (12237/12237), z dynamic and z select (1725). The two gate-drag scenarios
   differ by a few bursts, because the drag fractions land on a slightly
   different plot box. Deliberate differences:
   - Min and Max open for typing on a double click. A double click on
     Parameter deletes the row.
   - No row numbers.
   - Send to Napari is disabled with a reason, and there is no installer
     prompt.
   - Menu rows have no tooltips.
   - The `pick_population` "refused" shot shows the working pick.
2. **One gate list.** `core/gates.GateList` (ndxplorer `8a6d77e`, `2ae93e8`) is
   the Selection table in *both* GUIs. A mask or region row keeps its object
   as `GateRow.selection`, and `stored_selections` is gone. The Qt table is
   rebuilt from the list and writes its edits through `GateList.edit`, and
   `plot_control.get_selections()` is `gates.selections()`. The API change:
   `addMaskSelection`, `addRegionSelection` and `add_region_selection` became
   `plot_control.add_selection_object(sel)`.
3. **Fixed rather than copied** (both marked "Qt: broken"):
   - **Pick population.** The fit is `core/population_pick.fit_population`,
     and both GUIs use it (the Qt fix is `dbc4891`). It works in
     display-scaled units: it climbs to the local density maximum, grows the
     population downhill to 25 % of the peak, and divides out the
     truncation. A Qt canvas click now goes through the histogram edges,
     because the view box is in bin indices.
   - **Draw Mask.** `core/mask_paint.MaskCanvas` does the painting. The Qt
     side's painting is still broken (`PGImageWidget.invTransform`
     NameError), and nobody owns that fix. The Qt GUI is to be deleted.
4. **Browser, not yet run in a page.** The selection code imports without Qt
   (a subprocess test checks this). In the browser, "Send selection to" and
   "Send to Napari" are disabled and give the reason. Copy uses
   `emtk.clipboard` (the host hook, then `navigator.clipboard` under
   Pyodide, then pbcopy/clip/xclip). Load/Save Mask use `tttrlib.imread`
   and `tttrlib.imwrite`, so they wait on the tttrlib Pyodide wheel.
5. **Performance, measured.** One recompute with an interval pair, a G2D gate
   and a dragged z range takes ~4 ms at 1e5 rows and ~15–20 ms at 1e6. The
   recompute runs at most once per frame, however many changes arrive. That
   frame coalescing is the debounce, and it needs no timer. A pick takes
   ~15 ms at 1e5 rows and ~140–200 ms at 1e6 (a one-shot action).
6. **Open:** `z_add_selection` "during playback the slice is added as a gate
   too" (playback group, `on_z_select`). The ChiSurf RPC client of the emtk
   app is never set: `app.chisurf_rpc` is `None`, so Send always says "No
   ChiSurf connection". The `--chisurf-rpc` CLI flag does not reach
   `NdxApp` yet.

emtk additions: `DataTable` Select All (`also_selected`, `select_all`,
`selected_indices`), where Delete removes every selected row and a right click
inside the selection keeps it (`b945263`, `4699396`), and `emtk.clipboard`
(`93a9a8c`).

Tried and reverted: a Mahalanobis re-centring fit (grow the ellipse and divide
out the truncation at each pass). On the MFD data, clicking the diffuse FRET
cloud absorbed the dense donor-only population next to it: 9584 bursts in
one ellipse. The density-watershed search replaced it.

### overlays (Parameters, Overlays, curve fit, Equations, Table Editor)

Re-measure with `python -m ndxplorer.app.capture -s overlays_curve -s overlays_equation_list
-s curve_fit_dialog -s parameters_panel -s add_parameter -s equations_panel -s store_editor`
and `pytest ndxplorer/tests/test_app/test_overlays.py`; the Qt side with (offscreen)
`ndxplorer/tests/test_ui/test_curve_fit_overlay.py test_curve_fit_dialog.py
test_store_editor.py test_equation_editor.py` and `test/test_curve_overlay_update.py`.

1. **Parity status, 2026-09-23: all seven scenarios PARITY** in `parity/report.html`
   (features.md ticked; deliberate differences written there). The static FRET line
   is drawn where the Qt one is; 59 equations, all valid; 12,237 rows × 58 columns.
   Fixed rather than copied: the equation list reads the *user's*
   `curve_equations.yaml` first (Qt read the shipped file first); Names & functions
   lists only the functions ndX's engine accepts (`abs`), not chisurf's.
2. **Trap -- a green test run can be a skipped one.** A chisurf `FittingParameter`
   needs chisurf's compiled port runtime (IMP.bff). When it cannot load (every
   browser; a desktop mid-rebuild, as on 2026-09-23 ~09:45 when `_IMP_bff.so` and
   `libimp_bff.0.dylib` came from different builds) the feature degrades on purpose:
   the constants become plain numbers (edits still recompute), curves and the fit are
   off, and the Parameters/Overlays tabs say why. The chisurf tests in
   `test_overlays.py` then *skip*; check that `overlays._has_chisurf()` is true before
   reading a pass as a measurement.
3. **Blocked for the browser: chisurf parameters.** Curves, the curve fit, links and
   bounds need `chisurf.core.fitting.parameter`, which needs IMP.bff; there is no
   Pyodide build of it. Unblocking needs either an IMP.bff Pyodide wheel or a pure-
   Python parameter model for chisurf's port runtime. Everything else (constants as
   numbers, equations, Table Editor) is Qt-free and chisurf-free.
4. **chimol, answered.** The Qt window needed `~/dev/chimol` only through
   `chisurf.gui`: autoform / the parameter table -> `chisurf.gui.widgets.fitting` ->
   `chisurf.gui.widgets.experiments` -> `chisurf.core.structure` ->
   `chisurf.core.fio.structure.coordinates` (`from chimol.io.atoms import ATOM_DTYPE`).
   Without it `NDXplorer._deferred_init` dies in the Gaussian panel's autoform
   *before* the constants table exists, so the equations run without constants --
   that is the "equation columns silently missing". chimol is already an explicit
   chisurf dependency (`pixi.toml`, editable install); the harness adds it to
   `PYTHONPATH` only because it runs from sources. The emtk app imports no
   `chisurf.gui` and needs no chimol; `test_overlays.py` loads the MFD folder with
   chimol blocked and finds the equation columns.
5. **Open.**
   - View > Parameters / Overlays hide the tab's content, but `frame._draw_left`
     still draws those two titles (disabled) when no feature provides them (core).
   - The fit runs on a thread on a desktop. A fit with a freed constant rewrites the
     plotted columns from that thread while frames draw; the model only re-bins when
     something invalidates it, so nothing races today, but any per-frame reader of
     those two columns would.
   - The Qt Parameters table still comes from `chisurf.gui` (legacy, deleted with
     the Qt GUI).

Qt-free logic both GUIs call (moved, not copied): `core/overlay_curves.py`
(CurveEvaluator out of `plotting/curve_overlay.py`, parameter names, filled text,
predefined list, sampling, CSV, `OverlayCurve`), `analysis/curve_fit_setup.py`
(`plot_main.build_curve_fit_for` / `_build_cloud_fit` / `build_data_parameters`
behind a `FitHost`: `plot_main` is one, `ModelFitHost` the other; the dialog's
targets, reductions and result line), `core/equation_table.py` (rows, validation,
YAML, names), `core/store_edits.py` (`apply_edits`). `core/constants_group.py` and
`core/curve_parameters.py` stay the model. emtk: DataTable right-click
`context_call`, value shading `colour_source`, `column_filters`, sideways scrolling
(`min_column_width`), `fit_columns()`, `reserve` for an expanding table
(`d80bb85`, `1d3462d`). Core: `capture.py` adds the final `main` shot the Qt harness
always takes (`6bf25d1`); View > Equations reads `show_equations` (`8e1b805`).

Tried and reverted: building a table's rows afresh every frame -- the data table
rebinds on a new list and lost its sort order and selection each frame; rows are
handed out through a cache that returns the same list while the content is equal.

### playback_export (playback, find projections, publication export)

Re-measure with `python -m ndxplorer.app.capture -s playback -s playback_image_frames
-s publication_export -s find_projections -s find_projections_z -s find_projections_iris`
and `pytest ndxplorer/tests/test_app/test_playback_export.py` (16 tests, including
a cooperative ranking run, which is the browser's path, and a check that no Qt is imported).

1. **Parity status, 2026-09-23.**
   - `playback`: done. 87 of 12237 bursts at step 5 of 20, the same as the Qt window.
   - `playback_image_frames`: done for playback (Frame axis, 10 steps, Integrate).
     The shot's axes differ because image mode on open belongs to `open_image_h5` (io group).
   - `find_projections`, `find_projections_z`, `find_projections_iris`: done. Iris
     gives the same six scores as the Qt window and petal width × petal length is applied.
   - `publication_export`: done.

   The deliberate differences are in features.md: Stop is labelled ■ in both GUIs
   (no font the emtk atlas or a browser has includes ⏸); the Speed default comes
   from the *user's* settings (40 fps from an old `frame_duration_ms` 25), while
   the Qt window reads only the packaged file; the Playback fold shows disabled
   without data instead of hidden; and the ranking is an in-app `DialogWindow`,
   not a second top-level window.
2. **Blocked on core:** `z_add_selection` "during playback the slice is added as a gate
   too". The feature implements `on_z_select()`; the core hook that calls it from
   `PanelModel.z_select` was requested (lead, 2026-09-23). Check that it calls into the
   feature, then tick the item.
3. **Browser run not yet taken.** Every module imports without Qt (tested). Ranking
   runs on `emtk.tasks` in 10 ms slices (a `_Handle` whose `is_cancelled` also turns
   true at the end of a slice, so `run_vizrank` hands back its batch and the next slice
   resumes from the shared state iterator). Export needs matplotlib, which Pyodide
   ships, and goes to `app.io_service.save_bytes` (a download). What has not been done
   yet is a real page load via `emtk.web` that clicks Play, Start and Export.
4. **Clusters as ranking classes** are read from any feature's `cluster_labels`
   attribute. The analysis group must expose its labels under that name, or
   "Clusters" is never offered.

Tried and reverted: a hand-drawn `ToolWindow` in the feature (title row, drag,
✕, opaque body; an emtk window paints no background). It was replaced by
`emtk.dialog_window.DialogWindow`, which does the same and is shared by every
feature. Reading
the ranking's help/guide by importing `ndxplorer.ui` builds Qt dialogs, so the
files are read by path instead.

### io (open, merge, image mode, working path, burst IDs, selection files, screenshot)

Re-measure with `python -m ndxplorer.app.capture -s startup_empty -s file_dialog_analysis_folder
-s merge_dialog -s open_csv_iris -s open_csv_file_dialog -s open_bur_cli -s open_sampling
-s open_analysis_file_error -s open_image_h5 -s save_burst_ids -s selection_save
-s browse_working_path -s screenshot_button`, then run `pytest ndxplorer/tests/test_app/test_io*.py`
(35 tests) and, for Qt offscreen, `ndxplorer/tests/test_ui ndxplorer/tests/test_workflows
ndxplorer/tests/test_cli.py`.

1. **Parity status, 2026-09-23: all 13 scenarios are captured, and every io item is ticked**
   in `tools/parity/features.md`. The one item left open is open_image_h5's "Frame drives
   playback", which belongs to the playback group. The deliberate differences:
   - A load error shows the reader's reason, not the Qt traceback.
   - Screenshot saves the whole window, as Qt's `grab()` does. It is not copied to the
     clipboard.
   - BID is enabled only for a table with First/Last File and First/Last Photon.
   - The Process-Burst-IDs follow-ups say that the correlator and the microtime
     histogram are ChiSurf plugins.
2. **`app.io_service`** (`features/io_service.FileService`) is the one file service.
   - The API is `ask_open`, `ask_save`, `ask_folder` and `save_bytes`. Answers come
     through a callback. `answer()` presses a dialog for tests and replays.
   - On a desktop the dialogs are emtk FileDialogs in a `DialogWindow`.
   - In a page they open on `/mnt/local` (the mount), else `/mnt/dropped`. `save_bytes`,
     and any save outside the mount, becomes a download (emtk `emtk.web.page.download`).
   - The settings and playback_export groups already use it.
3. **Qt-free, shared (moved, not copied).**
   - `io/loading.py` holds the importers (dialog caption, file or folder, filters, merge
     title), the drop dispatch, the reader for each kind, the worker load, the merge
     question and its answers, and the working path and title rules.
   - `utils/axis_helpers.image_axes`.
   - `io/writer`: `save_burst_ids_headless(progress=)`, `find_bst_files`,
     `find_setup_name`.
   - `export/screenshots.py`.
   - `region_selection`: interval gates save and load without ChiSurf.
   - `file_operations.open_files` keeps only the Qt dialogs and the worker.
4. **Fixed on the way.**
   - A `.bur` line's trailing tab no longer becomes a parameter named "". The emtk axis
     chooser had picked it for x.
   - The emtk file dialog's save-mode name field was not drawn, because
     `set_next_item_width(-1)` gave it a negative width. The fix is emtk `0a64a62`.
   - Opening a `.pto` or `.h5` without an importer used to fall to the CSV reader.
5. **Browser, not yet run in a page.**
   - Nothing under `features/io*` imports Qt (a test checks this).
   - Loads run unthreaded in a page, on the next frame.
   - Saving a drawn region or a mask to `*.selection.json` needs `chisurf.core.roi`,
     which a page does not have. Interval gates work without it.
   - A real `emtk.web` page load that drops a file, mounts a folder and saves is still
     to be done.
6. **Asked of the core (lead).**
   - `model.read_path` (drop and `--file`) duplicates `io.loading.kind_for_paths` and
     reads a `.pto` with the burst reader. It should call `io.loading.read`.
   - `frame.open_dialog`/`_draw_dialog` and the core open actions are shadowed by io's
     and can go.
   - `pyproject` package-data does not list `ndxplorer/app/**/*.json` (views and feature
     specs), so a wheel would ship without them.

emtk additions: `view_form` choice `style: "radio_list"` (`0ccf122`), `emtk.web.page.download`
/ `in_browser` (`d906b00`), and `Layout.row` negative widths (`0a64a62`).

Tried and reverted: an `im_widgets.begin_modal` in emtk (dim, chrome, title bar). It was
dropped before its commit because `emtk.dialog_window.DialogWindow` landed at the same time
and does the same thing.

### analysis (Find structure, UMAP, Gaussian Fit)

Re-measure with `python -m ndxplorer.app.capture -s clustering_dialog
-s column_selection_dialog -s clustering_kmeans_run -s clustering_pca_run -s umap_run
-s view_umap_action -s gaussian_fit -s gaussian_select -s gmm_settings_dialog` and
`pytest ndxplorer/tests/test_app/test_analysis_app.py
ndxplorer/tests/test_app/test_analysis_logic.py` (28 tests: clustering as a cooperative
`emtk.tasks` task, cancel, the browser's UMAP text, PCA report, seed orientation, fit with
a held centre, save/load, settings, and a check that no Qt is imported). Trap: the
Gaussian tests need `chisurf.core.fitting.parameter`, which needs IMP.bff. While
someone rebuilds IMP.bff they fail with an `_IMP_bff.so` symbol error. That is the
environment, not the port; `python -c "import IMP.bff"` tells which.

1. **Parity status, 2026-09-23.** All nine scenarios are ticked in features.md, with
   the deliberate differences noted there. The values match the Qt window:
   - K-means on iris finds 3 clusters, and the colour survives isolating a cluster (it
     did not in Qt).
   - PCA on the six MFD columns gives 29 %/27 %, 12089 rows fitted and 148 dropped.
   - The Gaussian fit gives x1 3.77419, σx,1 1.30578 and w1 0.617.
   - gaussian_select keeps 10257 of 12237 rows.
   The work is in Qt-free modules both GUIs call:
   - `analysis/structure.py`: the method table, the clustering and the UMAP
     embedding as generators of checkpoints, and the PCA report.
   - `analysis/gaussian_mixture.py`: EM, seeds, ellipses, marginals, files and GMM
     settings.
   - `utils/package_install.py`: conda/pip and `install_task`.
   - `io/writer.save_clustering_data`: now takes a progress callback.
2. **UMAP was verified outside arm64.** arm64 has no umap-learn, so `umap_run`
   records the install offer, as the Qt baseline does. A real run used umap-learn
   0.5.12 and pynndescent from a `pip install --no-deps --target` scratch folder on
   `PYTHONPATH`, with arm64 left untouched. It covered columns, the progress log, Plot
   2-D and Plot 3-D. To re-check, do the same, or accept the in-app Install, which runs
   `conda install umap-learn -c conda-forge` into the env as a task.
3. **Browser run not yet taken.** Every module imports without Qt. What is missing:
   - K-means, HDBSCAN and PCA fall back to scikit-learn when `chisurf.core.ml` cannot
     be imported. This code path was never run under Pyodide.
   - UMAP says in words that it cannot run in a browser (numba).
   - The Gaussian Fit panel needs chisurf's `FittingParameter` (IMP.bff, native). In a
     page it shows the reason instead of the table. A browser Gaussian fit needs a
     parameter group that does not depend on IMP.bff, and there is none today.
   - A real `emtk.web` page load that clicks Run has not been done yet.
4. **Handed to others.** The selection feature outlines enabled Gaussian gates. This
   panel stops drawing a component once it is that gate (`GaussianPanel.is_gate`).
   `cluster_labels` feeds the ranking's "Clusters" classes (playback_export item 4).
   Docks becoming windows (window-manager agent) will move the Gaussian Fit tab
   from `tabs()` to a feature window.

Fixed on the way, in both GUIs:
- the seed width was read from the transposed bin;
- a saved `_gaussians.csv` did not load again;
- `_hist2d.csv` wrote y down the rows;
- Weight floor was never applied;
- Log Gauss did nothing;
- GMM Settings never opened;
- View > UMAP raised AttributeError;
- three installer offers imported `deps_installer` from the wrong package.

emtk gained:
- `emtk.tasks`;
- `emtk.dialog_window.DialogWindow`, now used by several features;
- in view_form, `special_text`, `label_source`, per-button `hidden_when` and the
  `progress` section;
- newlines in `text_wrapped`.

### settings (Settings menu, View > Axis Control, File > Make Report, Help)

Re-measure with `HOME=<scratch> python -m ndxplorer.app.capture -s menu_settings -s menu_view
-s menu_help -s set_default_axis -s load_settings_dialog -s save_axis_settings_dialog
-s performance_settings -s axis_control_dialog -s report_tool` and `pytest
ndxplorer/tests/test_app/test_settings.py test_settings_logic.py test_plot_axis_display.py
test_feature_hooks.py` (33 tests). Qt, offscreen: the whole non-app suite (864 passed). The
trap: set_default_axis, Save constants and performance Apply write `~/.ndxplorer`, so
capture and test with a scratch HOME (the tests set one).

1. **Parity status, 2026-09-23: all nine capturable scenarios are captured and ticked.**
   fix_report_tool is `[-]`: `ndxplorer.fix_report_tool` never existed (a5a1b2a added a
   dangling import), the entry is gone from both menus (core 3cf8811), and the report
   tool's Report column, Clear Reports and Generate Reports cover a missing or stale
   report. Deliberate differences, in features.md:
   - Axis Control has no tick-size, title-size or bold fields: the app draws in emtk's
     font (user directive). The values stay in axis_labels.yaml.
   - Performance has no Plot Backend choice.
   - The report's folder list is single-select, with a Report column instead of the
     green highlight.
   - Help > Update tells you how to update; it installs nothing.
2. **What changes the plots.** `plotting/axis_display.AxisDisplay` is
   `app.model.axis_display`, and `app/plots.py` reads it:
   - ticks per plot and side, one side per axis (bottom/left win when both are on);
   - the x-top and y-right titles;
   - the title colour.

   **Open:** the y-top and z-plot titles are stored but not drawn, because the core
   draws no such titles. Adding them to `plots.py` would make those three switches do
   something.
3. **Qt-free, shared (moved, not copied).**
   - `settings/persist.py`: axis settings, default axes, constants (a rich file keeps
     its format), equations.
   - `plotting/axis_display.py`: the label file.
   - `utils/performance_config.save_performance_config`.
   - `export/report.py`: discovery, templates, histograms through the GUI-free
     `ExplorerModel`, matplotlib `Figure` to PNG bytes, CSV, axes_info, DOCX, clear.

   `settings_helpers.py` and `report_tool.py` keep only the Qt dialogs; the Qt report
   no longer builds a hidden NDXplorer.
4. **Fixed rather than copied.**
   - Report 2-D CSV/PNG were transposed: H is (n_y, n_x) and the report used it as
     (n_x, n_y). With equal bins this was wrong without an error; with unequal bins
     it raised.
   - Performance Reset reset nothing, and the plot backend was never saved.
   - Save settings > Equations was not connected.
   - Help, About and Update were not connected.
5. **Measured.** A report of the three packaged plots on the MFD folder takes 0.46 s per
   folder once warm (the first takes 0.8 s). The report tool runs one folder per frame.
   None of the Performance values changes a computation in either GUI, because nothing
   reads `PerformanceConfig`: either wire `histogram_threads` into tttrlib's fill or
   drop the dialog.
6. **Browser, not yet run in a page.** Nothing imports Qt (tested in a fresh
   process). Files go through `app.io_service`: the combined DOCX is `save_bytes`, and a
   report written into a folder reaches the disk only inside the mounted folder.
   python-docx is not in the arm64 env, so the DOCX path has not been exercised in the
   emtk app (the message says so).
7. **Delegation.** Save > Constants and Save > Equations call the overlays feature's
   `constants.save_parameters` and `equations.save_equations_file` when they are there
   (rich constants, the table's equations), and `persist` otherwise. Load settings hands
   constants over as a plain dict, which the Parameters tab takes over on its next frame.

emtk additions: `view_form` `kind: "color"` values (swatch, HSV picker, hex) and the
`code_editor` section (a TextEditor bound to an attribute), in `dfb7823`. Core hooks
added on the lead's request: a capture op that returns False passes the step on, and a
target locator that returns None falls through (`039f918`); `files_dropped` (`9490acb`);
`plots.py` reads `axis_display`.

Tried and reverted: `emtk.begin_modal` for the dialogs. It left before its commit, and
`DialogWindow` replaced it. A Qt-sized dialog (resize_dialog to 460x1500) left a
half-empty window, so resize is a no-op and the dialogs are sized to their controls.
