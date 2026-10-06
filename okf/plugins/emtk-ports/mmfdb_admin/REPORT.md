# emtk port report — `mmfdb_admin` (DONE 2026-10-06)

Status 2026-10-05: **not ported yet.** The Qt baseline is captured and the Qt-free
pieces the native app needs are extracted; the native app (`gui/app.py`, model, view
spec, tests, after-images, docs, guide, help) is not written. `manifest.json` has
**no** `entrypoints.emtk`, so the ribbon still opens the Qt tool (correct: never point
it at an unfinished app). Agent board: T-20261005-MMFDBEMTK.

## Result

`core/mmfdb_admin` opens the native emtk app (`gui/app.py` over `gui/native/*`, view specs
`gui/admin.view.json` + `gui/admin_panels.view.json`, `gui/guide.json`, `gui/help.md`);
the manifest has `entrypoints.emtk`, the Qt `gui/tool.py` stays as legacy `entrypoints.gui`.
Commits: d6d2b2fe5 (Qt baseline, Qt-free pieces), emtk 7751e7d (widgets), 27b7e0029
(native app + model/click tests), 87b42ec0b (Qt-free import, status line, menu tests),
b5480a642 (docs: `docs/guides/102_mmfdb_admin.md`, `docs/concepts/measurement_database.md`),
and the closing commit (menu tooltips, panel-description fit, `test_native_app.py`,
after-evidence, entrypoint).

**Parity** (`compare.json`, `test.gui.emtk_port_parity` format): 457 controls before (union
over 35 panels + dialogs), 1010 after, **0 lost**, 0 without tooltip, Qt-free check OK.
Nine before-items are explained in `deliberate.json` (data of the before-image or renamed
text — e.g. 'Next ▶' → 'Next', a wrapped sentence, the catalogue combo's option count).
After-images: `after_<panel>.png` / `after_dialog_*.png` (53), read by the porting agent;
`after_entities.png` and `after_dialog_password.png` re-read by the coordinator.

## Where to pick this up

1. Delete the Qt `gui/tool.py` and its Qt-only views once the owner accepts the port
   (nothing native imports them; `optical_components/__init__` is lazy so `duplicates`
   stays Qt-free).
2. Table selection is not mirrored into the Protocols / Studies / Reagent Lots tables
   when the model selects programmatically (entity panels and Spectra do it via
   `_sync_selection`).
3. Re-capturing the after half (`capture_emtk_populated.py`) costs ~50 min (PNG encoding
   of ~50 states); run it in the background.
4. `chisurf/gui/widgets/spectrum_view.py` keeps its own copy of the spectrum-trace
   conversion (`core/fluorescence/spectrum_traces.py` is the shared one); touching it
   obliges porting its `.native` pyqtgraph calls, which needs chiplot axis-styling and
   legend-colour APIs first.

The planning notes below this section are history from the first pass.

## Before-images (Qt, seeded temp DB, 1200x800), read

`before_<panel>.png` for all 35 panels, `before_provenance_graph_loaded.png`,
`before_dialog_{connection,password,analysis_details,duplicates}.png`. Re-capture:
`QT_QPA_PLATFORM=offscreen PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.:$HOME/dev/emtk" python okf/plugins/emtk-ports/mmfdb_admin/capture_qt_populated.py okf/plugins/emtk-ports/mmfdb_admin`.

## Traps met

- `python -m test.gui.emtk_port_parity before mmfdb_admin` builds the widget without a
  client (real endpoint, panel 0 only); use the capture script.
- The Qt widget keeps hidden legacy tabs with `parent=self` detail widgets; inventory
  only `isVisible()` widgets.
- The mmCIF metadata key combos (thousands of items) are recorded as `combo with N options`.
- `chisurf/gui/widgets/spectrum_view.py` keeps its own copy of the trace conversion:
  touching it obliges porting its `.native` calls, which needs chiplot axis-styling and
  legend-colour verbs first (`test/chiplot_native_allowlist.txt`). Left untouched.
- `open(dst, "w").write(f(open(src).read()))` with src == dst truncates first.
- emtk `data_table.py` carried a peer's uncommitted hunk (FLEX_MIN); the emtk commit
  was built as HEAD + my hunks.

## Tests

`pytest chisurf/plugins/core/mmfdb_admin` → 121 passed after the extractions;
`test/gui/test_metadata_editor*.py` → 13 passed; emtk `tests/test_view_form_text.py`
and `tests/test_ui_data_table_links.py` green (each seen failing with the feature off),
existing view_form / data_table suites green.
