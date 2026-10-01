# trace_browser, card T1: native Setup stage

Agent: implementing agent, 2026-10-01. Commits: `73c12c9e5` (code and tests), the second commit "trace_browser T1: evidence and report" (evidence, this report, log hunk). Board claim: `T-20261001-TB1` in `okf/agent-board.md`. The Qt baseline is T0's `before*.{png,json}` (not changed); `T1/before.json` is a byte-identical copy (`cmp` is silent) so that the tool can read it.

Port type: B (Qt only), card T1 of 5. The manifest is **not** switched (no `entrypoints.emtk`); the card is checked with `--entry chisurf.plugins.tttr.trace_browser.gui.app:make_app`.

## State at start
`git status --short -- chisurf/plugins/tttr/trace_browser` printed nothing. Last live claim on the board was T0 (DONE).

## What the Setup page does (the Qt behaviour reproduced)
| Qt tool (`widget.py`) | emtk app (`gui/app.py`, `gui/model.py`) |
|---|---|
| Page 0 = `DetectorWizardPage` with the saved setups (the page selects the **last used** one, else its built-in default detectors) | page `setup`: the shared `chisurf.emtk.channel_definition.ChannelDefinitionWidget` in a window "Setup definition"; the saved setups are read from the same store as the Qt page (MMFDB first, JSON fallback; `ChannelDefinition.refresh_setups`), the last used one (`store.load_setups(...)["last_used"]`) is selected at start; with none saved the page starts empty |
| *Continue* (`_on_continue`): `model.apply_setup(page.get_settings(), page.filetype)`, hide page 0, show page 1 | `Continue` button -> `TraceBrowserModel.accept_setup(editor.model.get_settings())`: `apply_setup(settings, filetype_of(settings))` (the model code the Qt tool already calls), then `model.page = "browser"` |
| file type = the combo text, `Auto` -> `None` | `TraceBrowserModel.filetype_of(settings)`: `tttr_reading.file_type`, `auto`/`Auto`/missing -> `None` |
| `selected_channels` = sorted union of every detector's `chs` (`apply_setup`, T0), `None` if none | unchanged: the same `apply_setup` |
| *Select setup* (`_on_back_to_setup`): hide page 1, show page 0; nothing reset | `Select setup` button -> `model.back_to_setup()` (`page = "setup"`; accepted setup kept, editor keeps its state) |
| `_build_channel_labels` (in the widget) | cut and pasted into `TraceBrowserModel.build_channel_labels` (body unchanged, docstring added); the widget method is a one-line delegate |
| remembers: `last_used` in the setups file (written by the wizard when a setup is selected). Window geometry is the dock host's `plugin_trace_browser_settings.ini` (not the setup page) | `export_settings()` / `restore_settings(dict)`: `setups_file`, `setup_name`, and the working `setup` (JSON-safe copy of `get_settings()`); restoring only the file selects the last used saved setup again; `{}` gives the empty page |
| Page 1 = the browser | page `browser`: window "Trace browser" with `← Select setup`, the sentence "The trace browser stage (...) is not ported to emtk yet.", and three lines read from the model: accepted setup name, selected channels (or "auto-detect"), file type. No other data (rule 8a). |

Deliberate differences of this card (decisions for the reviewer):
1. **The emtk app starts on the Setup page.** The Qt constructor calls `_on_continue()` itself, so the Qt tool opens on the browser with the page's default setup. A placeholder as first view is useless in an unfinished card, and the PRD asks the Setup page empty/with a setup first. T2 may decide to start on the browser when a setup is remembered.
2. **Defaults.** With nothing saved the Qt page shows built-in detectors `green/red/yellow` (channels 8,0,3 / 9,1,2), PIE windows and file type `SPC-130`. The shared editor starts empty with type `auto` (as the other emtk apps embedding it). Continue with an empty setup gives `selected_channels = None`, and the model auto-detects channels from the files (T0 behaviour).
3. **Shared-editor limits seen on the screenshots (not changed, reviewer's call):** the TTTR-format list is fixed (auto, SPC-130, SPC-600_256, PTU, HT3, PT3, HDF, PTO), so ten tttrlib container names of the Qt list (brighteyes-ttr, cz-raw, flimlabs-itt1/stt1, photon-hdf5, pie-mfd, sm, smfret(2-color), spc-600_4096, spc-qc) cannot be chosen (listed in `deliberate.json`); the reading tab shows `0.000` for the macro/micro-time ticks when the saved setup has none (the real "ALEX Suite (auto)" holds only file type, binning and excitation period; Qt filled 50.0/50.0 from its built-in defaults).

## Files
New: `gui/app.py` (`TraceBrowserApp(ImApp)`, `make_app()`), `test/test_emtk_trace_browser_t1.py` (11 tests). Changed: `gui/model.py` (+96: `page`, `filetype_of`, `accept_setup`, `back_to_setup`, `build_channel_labels`), `widget.py` (-41/+1: `_build_channel_labels` now delegates). No spec/`view.json` (the page is the shared editor plus one button; the browser form spec comes with T2), no guide/help (T4), no manifest change, `gui/__init__.py` untouched (already Qt-free).

## The known quirk: which setups the page offers
Qt page: `load_detector_setups()` of the Qt module = MMFDB first, JSON fallback with one-time import. emtk app: `ChannelDefinition.refresh_setups()` = the same `store.load_setups` (MMFDB first). `last_used` comes from the same `store.load_setups`. Nothing is written at start-up except what the store itself does on first read (the JSON import into the MMFDB, as for the Qt page). Observed: with a **fresh** MMFDB and an existing setups JSON the import fails with `FOREIGN KEY constraint failed` (user row missing) in `setup_store.migrate_json_to_mmfdb`; the evidence and tests therefore take the setups from an explicit JSON file (`TraceBrowserApp(setups_file=...)`, no MMFDB involved). Not touched (shared store).

## Hermetic runs
Tests: an autouse fixture sets `CHISURF_SETTINGS_DIR`, `MMFDB_SETTINGS_DIR`, `MMFDB_DATABASE_PATH` to a temp folder and redirects the import-time constants (`DETECTOR_SETUPS_FILE` in three modules, `canonical_file` of two `SetupTypeConfig`s); setups come from a temp JSON. Evidence runs: the same three env variables on a temp folder, and a **copy** of `~/.chisurf/detector_setups.json` (read once) for the populated screenshots. `stat` of the real `detector_setups.json` and `flr/sample_management.db` before and after a run of the new test file: unchanged.
**Pre-existing finding (not mine, not changed):** the T0 tests `test_model_trace_browser.py` are not hermetic: running them changes the mtime of the real `~/.chisurf/flr/sample_management.db` (measured with `stat`; the Qt `TraceBrowser()` constructor, which opens the MMFDB, is the likely cause), and five of them depend on the user's real saved setup (with an empty settings folder `test_trace_matches_the_reference`, `test_load_trace_uses_and_fills_the_disk_cache`, `test_precompute_all_traces_reports_progress`, `test_trace_job_runs_on_a_snapshot` and `test_qt_widget_and_model_agree_on_the_same_folder` fail: the Qt page then starts on the built-in `SPC-130` default and the binning needs the saved ALEX setup). I tried a folder-wide autouse fixture and removed it for that reason.

## Tests
```
$ python -m pytest chisurf/plugins/tttr/trace_browser -q -p no:cacheprovider
55 passed in 20.57s          (44 before + 11 new)
$ python -m pytest chisurf/plugins/tttr/trace_browser/test/test_emtk_trace_browser_t1.py -q -p no:cacheprovider
11 passed in 10.07s
$ python -m pytest test/gui/test_emtk_port_parity.py test/test_prd_mentions.py -q -p no:cacheprovider
1 failed, 13 passed in 32.85s   (see Pre-existing failures)
```
The 11: every model key the app uses exists (no spec in T1); the Setup page draws empty and with a setup at 1200x800 and 800x600 (2 cases); Continue through the real button path applies the setup (channels `[0,1]`, type `PTO`), switches the page, the placeholder shows the accepted setup, Select setup returns and keeps it; Continue without a setup; Qt widget and emtk app derive the same `selected_channels`, file type and channel labels for two setups (2 cases: the real ALEX setup -> `[0, 1]`, an overlapping unsorted one -> `[0, 1, 2, 3, 8, 9]`); `Auto` file type; Qt-free proof (`qt_free("trace_browser", ENTRY)`); tooltips on both pages (`emtk_inventory`); settings round trip. Reference for the Qt side: the legacy `TraceBrowser` (offscreen) fed the same setup dict through `detector_page._load_data` and `_on_continue()`.

Deliberate breakage (made, run, restored; final run green): `apply_setup` without the duplicate check (`chs.append(c)` always) and `accept_setup` without `self.page = "browser"` together -> 7 failed: `test_continue_applies_the_setup_and_back_returns`, `test_continue_without_a_setup_auto_detects_channels`, both cases of `test_qt_widget_and_emtk_app_derive_the_same_channels`, `test_auto_file_type_means_every_supported_extension`, `test_every_control_has_a_tooltip`, `test_settings_round_trip`.

## Evidence (`okf/plugins/emtk-ports/trace_browser/T1/`)
```
$ CHISURF_SETTINGS_DIR=<tmp> MMFDB_SETTINGS_DIR=<tmp> MMFDB_DATABASE_PATH=<tmp>/mmfdb_test.db \
  python -m test.gui.emtk_port_parity after trace_browser --out okf/plugins/emtk-ports/trace_browser/T1 --entry chisurf.plugins.tttr.trace_browser.gui.app:make_app
after: 21 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/trace_browser/T1
$ python -m test.gui.emtk_port_parity compare trace_browser --out okf/plugins/emtk-ports/trace_browser/T1
{"lost": [], "untooltipped": []}
qt-free: True            exit=0
```
`compare.json`: `lost` 0, `explained` 113, `stale_explanations` 0, `gained` 16, `before_controls` 118, `after_controls` 21. The after inventory draws the empty Setup page, first tab only; so most Qt wizard items count as "not drawn" and are explained in `deliberate.json` by name: **113 entries**, each generated by a script that asserts the claimed replacement is drawn by the editor (checked by drawing every editor tab with the real ALEX setup): later cards (the browser toolbar, filter, table columns, Y range -> `card T2`; Export/CSV/DOCX/HMM/ndX/Time window/Help -> `card T4`; no `card T3` entry is needed, the plot has no label in the baseline), the setup editor's renamed controls (Save setup, Rename setup, Delete setup, Public setup, Calibration revision, TTTR format, Macro-time tick, ..., G factor, Routing channels, ...), controls the Qt tool hides (`Edit JSON`: `show_edit_json=False`; `photons`: a word of the hidden help text), digits (binning list items and channel cells), the ten missing format names (shared-editor limitation, open item), and `selectsetup` (drawn on the Browser page only).

Screenshots, all read at full size: `after_1200x800.png`, `after_800x600.png` (empty setup page: Continue, tab strip Setups/TTTR reading/Detectors/PIE windows/TAC corrections/Optical setup, setup drop-down `Unsaved`, empty name, buttons, calibration revision: no clipped text); `after_populated_setup_1200x800.png`, `after_populated_setup_800x600.png` (the real saved setup "ALEX Suite (auto)" selected, status "Selected setup: ALEX Suite (auto)"); `after_populated_{reading,detectors,pie,tac}_600x800.png` (the other tabs of the editor with the same setup; the narrow width makes the editor show its section drop-down, which is how a tab other than the first can be grabbed headless: reading `PTO`, detectors `green` channel 1 ranges `616:3784`, `red` 0, PIE windows `prompt` 616..3784, `delayed` 4278..7762; the long detector list scrolls); `after_browser_placeholder_{1200x800,800x600}.png` (the placeholder: notice, accepted setup, channels `0, 1`, file type `PTO`). Nothing overlaps or is clipped; the editor body does not fill the window height (empty lower part) because the shared widget draws only the open tab.

## Blocked / open (for the reviewer)
1. The emtk inventory flags 13 `input_float`/`input_int` controls on the editor's other tabs as having no tooltip (Macro-time tick, Micro-time tick, Microtime binning, G/l1/l2 factor, Start/End and Start/End TAC channel, Linear region start/stop, Microtime shift) although `ChannelDefinitionWidget` calls `set_item_tooltip` after each; not investigated (recorder or widget). The first tab, the one in `after.json`, is clean.
2. Shared-editor TTTR-format list shorter than the Qt list (item 3 above); zero macro/micro ticks for a setup that has none.
3. `migrate_json_to_mmfdb` on a fresh MMFDB fails with a foreign-key error (see the quirk section).
4. T0 tests are not hermetic (see above).
5. Decision for T2: the first view when a setup is remembered (item 1 above).
No emtk gap blocked the card.

## Pre-existing failures
`test/test_prd_mentions.py::test_prd_mention_allowlist_has_no_stale_entries` fails for `chisurf/plugins/calculator/kappa2_dist/gui/tool.py` and `chisurf/plugins/tttr/tttr_time_windows/tests/test_construction_smoke.py` (other streams; not touched). `test/gui/test_emtk_port_parity.py`: all pass.

## Docs
No docs change: the card is intermediate and the menu still opens the Qt tool; the guide, `help.md` and the docs page are card T4 (manifest switch).

## Review (reviewer, 2026-10-01)

Verified, not taken from the hand-over: commits touch only trace_browser files, the evidence folder and the agent's own
log hunk; a fresh `after --entry` gives 22 controls (21 in the agent's run: this account has "ALEX Suite (auto)" saved,
the agent's run had none; the difference is the setup name only), 0 untooltipped, Qt-free; `compare` exit 0, `lost` `[]`,
113 explained (51 shared-editor renames, 18 closed-dropdown items, 18 `card T2`, 13 `card T4`, 10 editor-format limits);
no Qt imports in `gui/app.py` / `gui/model.py`; constructing the app does not write to the real MMFDB; the Setup page
screenshots at 1200x800 and 800x600 read clean. **Accepted.** Findings and what was done:

1. **Tests were not hermetic — FIXED.** The T0 model tests touched the real `~/.chisurf/flr/sample_management.db` and five
   failed on a clean settings folder. The hermetic autouse fixture now lives in `test/conftest.py` for the whole test
   folder (T1's own copy removed; `ALEX` / `OVERLAP` setups shared from there). Five uncached-trace tests still need the
   legacy `IntensityTrace` Qt engine plus a real saved setup in a real MMFDB (with a fresh one it raises `KeyError: 0` in
   `intensity_trace/__init__.py:1523`, the fallback path indexing a dict with `[0]`); they are **skipped with that reason
   and card T3 must re-enable all five** against its Qt-free binner.
2. **"Foreign key" failure when loading a settings JSON into a fresh MMFDB — FIXED in core (reviewer).**
   `setup_store.save_setup_row` stamped `created_by_user_id` for a user the database had never seen, so on a new
   installation (or an unseeded `default_user_id`) the first setup save, including the one-time migration of a legacy
   `detector_setups.json`, failed with `FOREIGN KEY constraint failed` and rolled back; every tool that reads detector
   setups was affected. It now calls `db.ensure_user(user_id)` first (that method exists for exactly this). Two tests
   (`test/fio/test_setup_store_fresh_database.py`) fail without the fix; the six `test_container_cross_writer.py`
   failures in `test/fio` are identical on the committed code and unrelated.
3. **The parity recorder double-counted nested controls — FIXED (reviewer).** `input_float` is built on other wrapped
   widgets; the nested calls added phantom rows and the app's tooltip landed on the inner one, which is why 13 numeric
   inputs of the editor's other tabs were reported untooltipped although the widget sets a tooltip after each. Only the
   outermost control call and the app's own tooltip are recorded now (test added); the three accepted ports
   (`pch`, `region_mle`, `flc-2d`) re-run with identical inventories and 0 untooltipped.
4. Differences from Qt the agent listed (starts on the Setup page instead of the browser, empty editor with nothing saved,
   shorter TTTR-format list) are card T2 decisions: T2 decides whether to start on the browser when a setup is remembered;
   the 10 unreachable tttrlib container names are an emtk shared-editor limitation to be listed in the final report.
