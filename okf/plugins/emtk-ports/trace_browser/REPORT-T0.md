# trace_browser, card T0: model and de-duplication

Agent: implementing agent, 2026-10-01. Commits: `0e11d4c08` (Qt baseline), `f37e4b392` (model), third commit (evidence, report, log).

## State at start
`git status --short -- chisurf/plugins/tttr/trace_browser` printed nothing. Board claim: `T-20261001-TB0` in `okf/agent-board.md`. Baseline: `before.png`, `before.json` (118 controls) and populated grabs (`before_populated*.png`, `before_setup_page.png`), taken on a temporary copy of `~/dev/tttr-data/bh/bh_spc132_sm_dna/m000..m004.spc` (repo test data BH files are used by the tests).

## Findings the reviewer must know
1. **Pre-existing bug, behaviour kept.** The widget's CLSM image probe (`_is_clsm_compatible`) returns True for every readable TTTR with tttrlib 0.27.0 (`CLSMImage(...).intensity` is an empty `(1,0,0)` array, not None), so the Qt browser lists no real TTTR file (`before_populated_real_probe.png`: empty table). Only unreadable files are listed. The model reproduces this exactly (`probe_image`); `model.image_probe` and the widget's `_is_image_tttr` stay overridable. The populated baseline grabs patch the probe off in the driving script. A fix (treat as image only when `intensity.size > 0`) changes Qt behaviour, so it is left to the reviewer.
2. **Trace compute needs Qt.** `core.trace.load_trace` bins with `IntensityTrace().process_ptu`, and `IntensityTrace` is a QWidget (needs a QApplication, main thread). A cache hit is Qt-free; a miss is not. A `SnapshotJob` worker thread that computes an uncached trace hung my test run. For T3 a Qt-free binner (the logic of `process_ptu`) must live in `core/`; I did not add one (the card forbids new behaviour in `core/`). Tests fill the cache on the main thread, then run the job.
3. With a channel-only setup (`setup_settings=None`, `selected_channels=[0,1]`) `core.load_trace` returns an empty trace (the fallback passes ints to `_process_routing_channels`). Pre-existing; the real path is the setup (detectors) mode.
4. The widget's toolbar "Subfolders" checkbox (`gui/tool.py`) does not change `chk_subfolders`, so it rescans without effect. Pre-existing, untouched.
5. A reused widget keeps stale `setRowHidden` flags by row index across scans, so visible rows depend on history. The model has no such state; tests use a fresh widget per case.
6. `api/io.py:list_files` differs from the widget scan (pinned by `test_api_list_files_is_not_the_widget_scan`): fixed extension set without `.spc`/`.h5`, lists inside `.trash`, no image skip, other ordering/metadata keys. The widget behaviour is the model's.

## Files
New: `gui/model.py` (`TraceBrowserModel`), `widget.py` (git rename of the old package `__init__.py`, the Qt workspace, edited), `test/test_model_trace_browser.py` (34 tests). Changed: `__init__.py` (new, lazy PEP 562 shim exporting `TraceBrowser`, `StarCombo`, `StarRatingWidget`, `NoHoverSelectTable`, `META_FILENAME`, `get_tttr_supported_exts`, `name`, `cli_entrypoint`, keeps the `__name__ == "plugin"` hook), `core/trace.py`, `test/test_api.py`.

Why the move: `gui/model.py` imports through the package `__init__`, which imported Qt eagerly; the proof of Qt-freedom needs the package lazy, and the Qt code lived in `__init__`.

### Edits to existing files (as asked, exact)
`core/trace.py` (import move only; the Qt widget class is imported where it is used, on a cache miss, so `trace_signature`/`load_cached`/`cache_dir_for` import without Qt; behaviour identical):
```
-from chisurf.plugins.tttr.intensity_trace import IntensityTrace
 ...
     else:
+        from chisurf.plugins.tttr.intensity_trace import IntensityTrace
+
         time_window_s = window_ms / 1000.0
```
`test/test_api.py::test_the_ndxplorer_integration_is_actually_wired` inspected the source of the package; it now inspects `trace_browser.widget` (where that code lives). No assertion changed.

Legacy imports: grep shows importers of the old `__init__` are `__main__.py`, `__plugin__.py`, `gui/tool.py` (all `TraceBrowser`), `pyproject.toml` (`__main__:main`) and `test/core/test_plugin_entrypoint_resolution.py` (`...trace_browser.cli`). All resolve; `test_legacy_import_paths_still_resolve` proves the names. Removed on purpose: the private duplicates `_meta_path/_load_meta/_save_meta` (no importers).

## Tests
```
$ python -m pytest chisurf/plugins/tttr/trace_browser -q -p no:cacheprovider
42 passed in 9.94s        (8 existing + 34 new)
```
Reference numbers (comment in the test): pre-change widget `_compute_trace_cached` on a copy of `test/data/tttr/BH/132/BH_SPC132.spc`, ALEX setup: 10 ms: 6233 bins, per-series sums `[22443, 56257, 0]`, last time 62.32 s, max 467; 1 ms: 62329 bins. Scan/filter reference: the pre-change widget (loaded from git HEAD) on `fake_dir`, 10 combinations (subfolders x filter), pasted as `LEGACY_ROWS`. Widget-vs-model agreement: `test_qt_widget_and_model_agree_on_the_same_folder` (offscreen Qt, temp copy), plus rating/notes persistence through the widget, the image-probe agreement, the extension mapping, the SnapshotJob run, clear/clear caches, observers.

Deliberate breakage (each made, run, restored; final run green):

| Break | Tests that failed |
|---|---|
| `filter_accept`: `rating >= 2` -> `>= 3` | `test_scan_and_filter_match_the_legacy_widget[2-False]`, `[2-True]` (2 failed) |
| `rel_key` returns the bare file name | 6 failed: scan/filter `[0,1,2,4-True]`, `test_rating_and_notes_round_trip_through_metadata`, `test_qt_widget_and_model_agree_on_the_same_folder` |
| (tried) skip the explicit `flush_meta()` in `set_rating` | no failure: `meta_set` already pushes the metadata through the client; the flush is redundant (as in the Qt tool) |

Qt-free proof: `test_model_module_is_qt_free` (subprocess blocking `qtpy`/`PyQt*`/`PySide*`, builds the model and its client, asserts no `chisurf.gui` module): passes. The Qt tool still imports by old names and its populated grabs are pixel-identical to the baseline (5 of 6 identical; the 1 ms grab differs only in the star cells' antialiasing, read and compared by eye).

## What the model exposes
State: `current_folder`, `include_subfolders`, `setup_settings`, `setup_filetype`, `selected_channels`, `meta`, `files` (all scanned) / `rows` (after the rating filter; dicts `name, path, size, size_text, size_mb, rating, notes`), `filter_index` / `rating_filter` (label, `FILTER_LABELS`), `window_ms`, `y_min`, `y_max` (`y_range` ordered), `selected_files`, `current_file`, `trace`, `requests` (reserved for the T4 hand-off requests), `status_text`, `error_text`, `image_probe`. Methods: `apply_setup`, `allowed_exts`, `open_folder`, `set_include_subfolders`, `scan`, `set_rating_filter`, `apply_filter`, `accepts`, `clear`, `load_meta`, `get/set_rating`, `get/set_notes`, `flush_meta`, `set_selection`, `trace_signature`, `load_trace_cache`, `compute_trace_cached`, `load_trace`, `show_file`, `set_window_ms`, `precompute_all_traces(progress)`, `clear_caches`, plus `notify`, `add_observer`, `_observers`. Spec-friendly: ratings are ints 0..5 (plain choice column), `notes` is a text column. Hand-offs (ndX, Time window, transfer) are not implemented; T4 adds `request_*` methods that append to `requests`. Delete, export and the ndX/TW/HMM handlers stay in the widget until T4. Not changed: the stored rating range of the Qt star widget (0..3).

## Duplicates removed (measured by line ranges in git HEAD `__init__.py`)
`_meta_path/_load_meta/_save_meta`: 22 lines before, 0 after. `_human_size`, `_cache_dir_for`, `_trace_signature`, `_trace_cache_file`, `_load_trace_cache`, `_save_trace_cache`, `_compute_trace_cached`, `_is_clsm_compatible`, `_is_image_tttr`, `_allowed_exts_for_setup`, `_filter_accept` bodies (about 190 lines) are now one-line delegates (about 20 lines). Widget file: 2631 -> 2222 lines.

## What the Qt tool still does by itself
Table fill and sorting, star widget, hiding rows by row index, debounce timer, progress dialog, dialogs, drag and drop, Delete to `.trash`, Export/CSV/DOCX, the transfer handlers, `_build_channel_labels` (T1), plot.

## Blocked / open
Findings 1 and 2 above (probe bug; Qt-free binner for T3). Environment note: `IMP.bff` was briefly unimportable while another agent rebuilt it; retried, no effect on results.

## Review (reviewer, 2026-10-01)

Verified, not taken from the hand-over: commits touch only trace_browser files, its report and the agent's own log
hunk; the rename shows as `__init__.py` shrunk plus `widget.py` new; `core/trace.py` changed only by moving the
`IntensityTrace` import into the cache-miss branch; 42 tests passed (44 after the fix below); every legacy name
(`TraceBrowser`, `StarCombo`, `StarRatingWidget`, `NoHoverSelectTable`, `META_FILENAME`, `get_tttr_supported_exts`,
`name`, `cli_entrypoint`) still resolves. **Accepted**, with these decisions:

1. **Image probe bug — FIXED (reviewer).** Reproduced: with tttrlib 0.27.0 `CLSMImage(tttr_data=...)` does not raise on a
   non-image file but returns an empty `(1, 0, 0)` intensity (a real scan, `Leica_SP8.ptu`, gives `(93, 512, 512)`).
   The probe tested `is not None`, so every readable TTTR was classed as an image and the browser listed no file at all
   (`BH_SPC132.spc` -> "treated as image: True"). This is a shipped Qt-tool defect that predates the port. The probe now
   requires a non-empty pixel stack (`gui/model.py::is_clsm_compatible`); two tests on the real sample files fail without
   the fix. The same probe pattern exists nowhere else in `chisurf/`. The agent's workaround (patching the probe off in
   the baseline script) is no longer needed; a fresh baseline would list the file.
2. **Trace binning needs Qt — decision for card T3.** `core.trace.load_trace` bins with `IntensityTrace`, a QWidget, so
   an uncached trace cannot be computed Qt-free (and hung a worker thread in the agent's test). Card T3 must first add a
   Qt-free binner to `core/` (counts per window from the photon macro times, same numbers as `IntensityTrace`, proven
   against it on `BH_SPC132.spc`), with `load_trace` using it; that is the one allowed `core/` change, as an additive
   function, and the Qt tool may keep its widget path until T4.
3. Quirks recorded by the agent (toolbar Subfolders checkbox without effect, stale hidden-row flags on a reused widget,
   channel-only setup gives an empty trace, `api/io.list_files` differs from the widget scan) are carried to the card that
   owns the control (T2) and must be decided there, not silently "fixed".

4. **Five uncached-trace tests skipped (reviewer, with T1).** They run the legacy `IntensityTrace` Qt engine, which reads its
   detector mapping from a real saved setup and wrote to the real database; they are skipped with that reason and card T3
   re-enables them against the Qt-free binner (see the review in `REPORT-T1.md`).
