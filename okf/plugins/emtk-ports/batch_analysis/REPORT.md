# emtk port report - `batch_analysis` (audit-all row 54, upgrade to verified parity)

Agent: claude (Sonnet), 2026-10-03, T-20261003-LEFTOVERS2, UPGRADE_BRIEF. Type A (the stream's app was a flat stub: typed fit name, no steps, no loaded-data pick, no file list). Verdict: **accept**.

Commits: `e0c0ea691` Qt baseline + stream state (`pre-upgrade/`), `cf4cd4f47` app + tests + shared stepper/hermetic fixtures, then the evidence/docs commit.

## 1. State at start
Stub `gui/app.py` (flat page: welcome, fit name as free text, CSV text field, Run, results as Markdown), `strings.py`, 3 smoke tests. `before_emtk_populated_*.png`: no steps, no Loaded data, no file list/Add/Drop, no Help/Guide, captions cut at the right edge.

## 2. Qt checklist (`before*.png`, `before_populated_1..5_*.png`)
| # | Qt control | emtk | |
|---|---|---|---|
| 1 | step list, check marks (Files & fit: fit chosen, Run: has results) | `emtk_wizard.draw_steps`, same conditions | yes |
| 2 | Back (greyed first) / Next / Finish (last) | spec buttons | yes |
| 3 | Welcome text | Markdown, same words | yes |
| 4 | Loaded data check list + Refresh, tooltip with curve preview | `data_table` with editable Use check box, Refresh; tooltip = file (no preview) | yes / preview deliberate |
| 5 | Files list, Files / Folder / Database / Remove / Clear, drops | file `data_table`, in-app FileDialog, DatasetPicker, host drops, Delete key | yes |
| 6 | Template fit choice | spec choice, names cached per step (+ Refresh fits) | yes (+) |
| 7 | Run: summary, Results CSV, `...`, Run batch, status | Markdown summary, field, Browse..., Run batch, progress bar, outcome line | yes |
| 8 | Run: progress dialog, message boxes (no data / no fit / complete / failed), save dialog if no CSV | bar `i/total: name`, red/green lines with the Qt texts, in-app save dialog then the run goes on | yes |
| 9 | Results table | `data_table` Run/Filename/Parameter/Fixed/Value/Chi2r, sort, filter | yes |
| 10 | per-run screenshot for the DOCX | `capture` seam (none by default) | deliberate: no Qt window to grab |
Gained: Help, Guide, tooltips everywhere, DOCX-missing line, CSV folder is created if absent (the Qt run raised).

## 3. Reuse
`chisurf/plugins/emtk_wizard.py` (new shared stepper + step list, usable by boarding/tr_anisotropy), `chisurf/plugins/emtk_hermetic.py` (new shared hermetic fixtures), `emtk_layout.button_row`, `emtk.view_form` + `data_table`, `emtk.file_dialog`, `chisurf.emtk.dataset_picker`, `chisurf.emtk.help_guide`, `emtk_test_input.Driver`, `project_browser` layout checker. Numbers: the unchanged `core/runner.py`. No fork; the dataset picker and file dialog are the shared ones. Flagged: boarding keeps its own copy of the stepper (not touched).

## 4. Evidence
`after: 18 controls, 0 without tooltip, qt-free=yes`; `compare` exit 0 (lost [] after `deliberate.json`: Qt emoji/label spellings). Screenshots: `after_populated_{1..5}_*_{1200x800,800x600}.png`, `after_file_dialog_*`, `after_help_*`, `after_tour_*`, `after_no_data_*` (fake session, labelled test numbers); docs figures from REAL fits of the ibh decays (`docs/guides/screenshots/batch_analysis_emtk.py`; chi2r 6.16 / 34.4 as in the guide).

## 5. Layout
Read at both sizes: no overlap or clipping (asserted per step populated/empty, `layout_problems` + `clipped_texts`), buttons at natural width, choice 420 px, long paths elided with full text in the tooltip, tables get the space, tour cards clear of targets (named header/button rects, `assert_tour_card_clear`).

## 6. Tests
`pytest chisurf/plugins/core/batch_analysis`: **71 passed**. Parity vs the live Qt tool: steps/titles/subtitles/conditions, welcome and summary text, dataset labels and ticks (Qt `LoadedDatasetSelector`), file lists (Qt `PathListWidget`: expand, dedupe, remove, clear), a whole run (CSV byte-equal, ZIP names, rows, dispatch log, parameters restored) against Qt `BatchViewModel.run`, results cells vs `results_html`, warnings/failure texts. Breakage twice (tick inverted, dedupe removed): 4 failures, restored.
Control -> test (real pointer/keys/wheel/drop): step list `test_a_click_on_each_step...`, marks `test_the_check_marks...`, Back/Next/Finish `test_back_and_next...`/`test_finish...`, Use box `test_a_click_on_a_check_box...`, Refresh `test_refresh_button...`, drops `test_files_and_folders_dropped...`, Files dialog `test_files_button_opens_a_dialog...`/`..._window_that_closes...`, Folder, Database, row/Remove/Delete/Clear `test_a_row_is_selected...`, wheel `test_the_wheel_scrolls...`, fit choice, Refresh fits, Run/CSV typed/Browse/cancel/greyed/progress, results sort+filter, Help, Guide walked with awaits at both sizes, card drag, small window flow. Guard: real `~/.chisurf` unchanged (`emtk_hermetic`).

## 7. Docs
`docs/guides/78_model_comparison_and_batch.md` (Batch section rewritten for the emtk UI, four figures regenerated, two known defects struck), `docs/reference/plugins/batch_analysis.md` (native window), `gui/help.md`, `gui/guide.json` (8 steps, 3 awaits).

## 8. Findings
Real: a CSV path in a missing folder crashed the Qt run (unhandled); completion marks went stale after a fit choice (fixed: re-evaluated per frame). python-docx is absent in the arm64 env, so the DOCX path is untested here (the window says so). Not touched: `chisurf/emtk/*`, emtk, preview gate.
