# emtk port report - `spectra_downloader` (audit-all row 91, emtk-only)

Agent: claude (Sonnet), 2026-10-03, board `T-20261003-EMTKUP7`. Verdict: **accept** with two recorded emtk gaps (section 8).

Commits: `40ff258a1` populated Qt baseline + earlier stream's emtk state, `be9e1275f` app/tests, then the evidence commit.

## 1. The Qt predecessor
Not absent: the Qt tool is `gui/tool.py` of git HEAD before the earlier stream replaced it (`SpectraTool`, a `NavigationPanelTool` over `OverviewPanel`, `SpectraBrowserWidget`, `DownloadPanel`, `AddToMmfdbPanel`; their modules are still in the tree). Source in `pre-upgrade/qt_tool.py.txt`; `scripts/capture_qt_populated.py` builds it from that text on a temporary staging DB (`before_populated_*.png`, 4 panels + narrow Browse; `before.json` from `scripts/qt_inventory.py`: 85 controls). The harness's own `before` cannot run (the manifest `gui` entry is the emtk app), the earlier `tests/renders/qt/*` are kept. `before_emtk_populated_*` is the earlier emtk app: labels right of fields and overlapping at 800 px ("Endpoint"/"Local MMFDB" over the path), a light custom style against the emtk default look, a hand-drawn table, no detail form, ports as drag fields, results as one JSON string in the message line.

## 2. Qt checklist
| Qt control | emtk | Test |
|---|---|---|
| nav list, search, Back/Next/⏩, status "Ready" | nav rows, Filter, Back/Next (grey at ends), status; ⏩ deliberate (no workflow step) | test_clicking_each_navigation_row..., test_the_navigation_filter..., test_back_and_next... |
| Overview fields, JSON text, Refresh | the Qt `overview.view.json` fields, two data_tables (category, source), Refresh | test_overview_counts_equal_the_qt_panel, test_overview_refresh... |
| Browse: Filter, Source, Category, "n / m", table, detail form, Properties, Metadata, spectrum, Push selected/all | spec fields, data_table (tick column + click row), the mmfdb-admin `fluorophore.view.json` detail, tabs, plot (wheel zoom), Push buttons with Yes/No and result/failure dialogs | the browse/push tests; rows, filters, detail and push arguments equal the Qt browser (test_browse_rows_filters_detail_and_push_equal_the_qt_browser) |
| Download: Available Sources, Run, Already scraped, Browse this source, log | spec choice, Run (greyed while running; stubbed subprocess), counts line, log editor | test_the_scraper_choice..., test_run_is_greyed..., test_browse_this_source... |
| Add: session line, Endpoint radios, Local MMFDB, Replace, Mark approved, Advanced fold (host, ports, user, password), Check session, Add all, log | the Qt `endpoint_auth.view.json` form (ports spin fields, password masked), Check session, Add all with the Qt log wording | test_check_session_and_the_local_import..., test_a_server_import..., test_the_advanced_fields... |
| Guide, help | Guide, Help, tour waits for the user | help/tour tests |

Deliberate (`deliberate.json`, compare exit 0, lost [], stale []): the Qt multi-row selection is a Push tick column plus a clicked row for the detail; the JSON box is two tables; Cancel/⏩ of the stepper; placeholders of unbuilt panels; Advanced contents are drawn when the fold is open.

## 3. Bugs and gaps fixed in the app
* Labels overlapped or clipped at 800 px and the custom light style departed from emtk's default look: spec forms, one label column, default style.
* Port fields were drag fields (a port could not be typed): spec spin fields 1..65535.
* Panel rows shared one widget id (`##nav`): only the first row answered a click.
* Tour card buttons did not answer (card under the other windows): the tour has a window of its own while a step does not wait.
* Add-to-MMFDB showed one JSON string; now the Qt log lines; the session line is the Qt sentence.
* `create_app()` without a db opens the repository's `spectra.db` (and migration backups appear in the plugin folder): all tests and the evidence scripts pass a temporary database or redirect `get_db`.

## 4. Network and hermeticity
Tests: temp HOME/CHISURF_SETTINGS_DIR/MMFDB_*, a staging DB in tmp, a socket guard that fails any connection (`test_the_socket_guard_really_blocks_the_network`), the scraper `Popen` and the MMFDB server client are stubs; the real `~/.chisurf` is snapshotted for spectra/mmfdb related files (other agents write other files there concurrently), logs and bytecode cache ignored.

## 5. Tests
`python -m pytest chisurf/plugins/spectra_downloader/tests`: new `test_emtk_spectra_parity.py` 38 tests + earlier suites; last full run 83 passed, 1 skipped, 2 strict xfails (the first tour card dead-button gap, the Enter gap) before the final re-runs; breakage twice (pick ignored, push argument inverted): 2 failed, restored. The earlier `test_real_native_clicks_navigate_and_select` and `test_populated_normal_and_narrow_table...` tested the removed hand-drawn table and were replaced by the real-input tests.

## 6. Layout
`after_populated_{overview,browse,download,add_to_mmfdb}_{1200x800,800x600}.png` read at full size: no overlaps, one caption column, wide forms; at 800 px the Browse detail stacks under the table and the plot is reached by the wheel (scrolling). 

## 7. Reuse / Docs
Reuse: Qt `overview.view.json`, `endpoint_auth.view.json`, mmfdb-admin `fluorophore.view.json` (by path), `emtk_layout`, view_form/data_table/code_editor sections, help/tour, `emtk_test_input`. Docs: `docs/guides/83_spectra_and_r0.md` text and both figures regenerated from the app on a copy of the real staging DB (`scripts/capture_docs.py`), `docs/reference/plugins/spectra_downloader.md`.

## 8. emtk gaps (repro)
1. Enter in an emptied `value` str field does not commit the empty text (a click away does): `type "alexa", Enter; click, Ctrl+A, Delete, Enter` leaves the model at "alexa" (strict xfail `test_enter_commits_an_emptied_filter_field`).
2. A tour card button lying over a `data_table`/editor never answers a press (as in plugin_check): strict xfail `test_the_tour_next_button_over_the_component_table_answers`.
3. (ptu_alex_creator report) a spin field does not consume the wheel notch; here the app clears the wheel at the end of the frame.
