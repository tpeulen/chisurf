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
