# emtk port report - `plugin_check` (audit-all row 80, upgrade to verified parity)

Agent: claude (Sonnet), 2026-10-02/03, T-20261002-LEFTOVERS, UPGRADE_BRIEF. Type A (earlier stream's emtk app existed, hand-drawn, no spec, no guide/help, no click tests). Verdict: **accept**.

Commits: `7d35f011b` Qt baseline + stream state (pre-upgrade/), `34a84ed29` bytecode removed, then the app/tests commit and the evidence/docs commit (hashes in the board status line).

## 1. State at start
Uncommitted: modified `__init__.py`, `manifest.json`; untracked `gui/app.py`, `gui/model.py`, `test/`. Copied to `pre-upgrade/`. Defects of the stream's app (`before_emtk_populated_*.png`): plugin names cut to the last menu segment, progress `3/0` before a sweep, "Delay between plugins" as a drag bar with the label cut, `builtin`, hand-drawn table, no details for untested plugins, no Help/Guide, 5 tests.

## 2. Qt checklist (`before.png`, `before_populated_*.png`, `qt_rows_*.json`)
| # | Qt control | emtk | |
|---|---|---|---|
| 1 | Test All Plugins / Test Safe Plugins (first 10, short timeouts) | buttons, greyed while running | yes |
| 2 | Refresh | button (rescans, clears results) | yes |
| 3 | Clear Blacklist | button | yes |
| 4 | Delay spin box 0-5 s step 0.1 default 0.5 | spec field with arrows, same limits | yes |
| 5 | Skip blacklisted (default on) | toggle | yes |
| 6 | Progress bar, status label ("N plugin(s) found - M dependency problem(s)") | spec progress + info line, same counts | yes (no emoji) |
| 7 | Tree Plugin / Status / Source / Depends on / Error (50 chars + ...) | `data_table`: same rows in the same order, same cells; sort, filter, column picker added | yes |
| 8 | Details: Plugin, Module, Source, Status, Requires, Optional, Problems, Description | details window, plus Version and Entry points | yes |
| 9 | Error box for a failed plugin | selectable read-only editor | yes |
| 10 | Status glyphs pass/fail/skipped/pending | words pass/fail/skipped/pending (+ Qt only, no GUI) | deliberate |
Gained: Stop, Help, Guide, filter, tooltips on everything, settings round trip.

## 3. Reuse
Shared: `emtk.view_form` spec + `data_table` (as plugin_manager), `chisurf.plugins.iter_plugins` + `core.plugin.dependencies.resolve` (the Qt tool's discovery, Qt-free), `chisurf/emtk/help_guide.py`, `plugins/emtk_layout.cap_widths`, `imaging_emtk.testing.Driver`, project_browser's layout checker. Duplicates replaced: the Qt tool's `_dependency_summary`/`_render` now call `model.dependency_summary/render_bounds` (one copy). Nothing forked.

## 4. Evidence
`after: 68 controls, 0 without tooltip, qt-free=yes`; `compare` exit 0 (lost [], untooltipped [], 134 explained = Qt tree cell texts + 5 named labels, stale_explanations 0). Populated shots come from a REAL safe sweep (10 child processes): `after_populated_{1200x800,800x600}.png`, `click_1..8_*.png` (start, sweep done, row selected, sorted, filter typed, Help, Guide, delay typed), `docs_failure_selected_1200x800.png` (a real failing factory).

## 5. Layout
1200x800 and 800x600 read at full size. Asserted by tests (`layout_problems`, `clipped_texts`): no overlap, nothing outside the window. At 800 the long menu paths are elided in the Plugin column (full name in the row tooltip and the details); Status/Source are whole. Delay field capped width, toggle under the fields' column, idle Stop greyed, progress `0/0` before a sweep, dock split re-proposed on resize.

## 6. Tests
`pytest chisurf/plugins/core/plugin_check -q`: **63 passed, 2 xfailed** (strict). Numeric parity vs the live Qt tool: rows, cells, order, sources, dependency summaries, problem list, details strings, 50-char error cut, glyph-to-word mapping, safe sweep = first ten, option defaults/limits; baseline JSON cell for cell. Breakage twice (error cut off by one; blacklist condition inverted): 1 and 4 failures, restored.
Control -> test (real pointer/keys/wheel via `Driver`, outcomes asserted): Test all `test_test_all_button_runs_every_plugin...`; Test safe `test_test_safe_button...`; greyed buttons `test_the_sweep_buttons_are_greyed...`; Stop `test_stop_is_greyed_while_idle...`; failed row + details `test_a_failed_check_shows...`; Refresh `test_refresh_button_rescans...`; Clear blacklist `test_clear_blacklist_button...`; Skip blacklisted `test_skip_blacklisted_checkbox...`; Delay typed/clamped/arrows/click-away/used `test_delay_*`, `test_a_typed_delay_is_used_by_the_sweep`; row click, arrow/Home/End keys, header sort, filter, wheel, column picker (right click), tooltips (hover) `test_a_click_on_a_row...`, `test_the_arrow_keys...`, `test_a_header_click_sorts...`, `test_the_filter_box...`, `test_the_wheel_scrolls_the_table...`, `test_right_click_on_a_header...`, `test_hovering_a_cell...`; error text select+copy / read-only `test_the_error_text_*`; dock divider drag `test_the_divider...`; Help/Guide buttons, tour walked with awaits, card placement, card buttons `test_help_button...`, `test_guide_button...`, `test_the_tour_is_walked...`, `test_every_guide_target...`, `test_the_tour_card_does_not_cover...`, `test_every_tour_card_button_that_is_not_over_the_table_works...`; host drop `test_a_file_dropped...`; small window `test_the_whole_flow_works_in_the_small_window_too`. Guard: module fixture fails on any change in real `~/.chisurf` except `logs/`; tests run on temp settings/HOME.
Strict xfails (emtk/shared-helper gaps, not edited): (1) a tour card button drawn over the data_table never fires, the table takes the press (repro: `PluginCheckApp`, click Guide, click "Close Tour" at x=722: the row under it is selected, tour stays); (2) Ctrl+A in the table filter box does not select its text.
Pre-existing failures: `test/test_plugin_help_guide_seam.py` 10 failures from other plugins (img_pixel_*, setup, clsm_generator, ...), none about plugin_check.

## 7. Docs
New `docs/guides/96_plugin_check.md` (+ index entries), figures `docs/guides/figures/plugin_check.png`, `plugin_check_failure.png` (from the emtk app, real sweep), `docs/reference/plugins/plugin_check.md` (surface, native window, guide link), `help.md`, `guide.json` (8 steps, 2 awaits). Allow-list line struck.

## 8. Findings
Real: `HOME` was not redirected for child checks (a plugin starting could write `~/.chisurf`): fixed. In a loaded machine a safe sweep's 5 s timeout fails slow plugins (Accurate FRET once); the full sweep uses 30 s.
