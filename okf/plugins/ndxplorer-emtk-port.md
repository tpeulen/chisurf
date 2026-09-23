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
