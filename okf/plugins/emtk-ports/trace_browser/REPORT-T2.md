# trace_browser, card T2: native Browser stage

Port by the implementing agent (Sonnet), 2026-10-01; the agent could not write this file, so the reviewer saved its
hand-over text, applied the rating-range correction and appended the review. Commits: `afb048248` native Browser stage,
`3584ced70` evidence and log, `60716e89b` rating range 0..3 (reviewer-requested). Board claim `T-20261001-TB2`.

Card T2 of 5 (T0 model, T1 Setup, **T2 Browser**, T3 plot + annotation, T4 export / hand-off / guide / manifest). The
manifest is not switched; the card is checked with `--entry chisurf.plugins.tttr.trace_browser.gui.app:make_app`. The Qt
baseline is T0's `before*.{png,json}`; `T2/before.json` is a byte-identical copy.

## What the Browser page does

`gui/trace_browser_emtk.view.json` drawn by `emtk.view_form.draw_form` in the left window "Trace browser"; the right window
"Trace plot" is a labelled placeholder (selected file name and bin window only, no data).

| Qt control | emtk Browser page |
|---|---|
| `← Select setup` | `button_row` `back_to_setup` (setup, folder, rows and selection stay) |
| folder label | read-only `value` `folder_text` |
| `Open` | `button_row` `choose_folder` -> `FileDialog` (folder mode) -> `model.request("open_folder", path)` |
| drop of a folder | `on_paths_dropped`: the first dropped folder opens; a file or a missing path is ignored with a status text |
| `Include subfolders` | `toggle` `include_subfolders`, `call` `set_include_subfolders` (sets the flag and rescans) |
| rating filter | `choice` `rating_filter`, `options_source` `filter_label_list` |
| `N ms bin` | `value` `window_ms` (stored and remembered; no trace until T3) |
| Ymin / Ymax | `value` `y_min`, `y_max` |
| `Clear`, `Clear caches` | `button_row` `clear`, `clear_caches` |
| file table | `custom` `data_table` over `model.rows`: File, Rating (editable), Size (MB), Notes (editable); `selected_call` `select_row`, `edited_call` `edit_cell` |
| status | `info` `status_line` |

Selecting a row sets the selection and current file only (no trace, no cache folder). Rating and notes write through
`set_rating` / `set_notes` into `.trace_browser_meta.json` (flushed at once; Qt debounced 300 ms). **Rating range: the Qt
`StarRatingWidget` has 3 stars and `StarCombo` offers 0..3, so the Rating column accepts a whole number 0..3 and refuses 4
and above, 2.5 and non-numbers (an earlier 0..5 came from a wrong line in the survey).** While a scan runs every control is
greyed and table edits are put back. Scanning runs on a `SnapshotJob` through the model's `runner`.

### Quirk decisions (reviewer's, carried out)
(a) the Subfolders checkbox now really works (one checkbox sets the flag and rescans; the Qt toolbar one did nothing);
(b) the app opens on the Browser page when a last used or restored setup exists (as the Qt constructor's `_on_continue()`),
otherwise on the Setup page; Continue after a changed setup rescans an open folder (Qt keeps the old list);
(c) `api/io.list_files` is not used (a test pins it); (d) stale hidden-row flags of a reused Qt widget are not ported.

## Persistence

`export_settings()`: `setups_file`, `setup_name`, `setup` (T1) plus `folder`, `include_subfolders`, `rating_filter`,
`window_ms`, `y_min`, `y_max`. The Qt tool remembered none of these (only dock geometry). `restore_settings` ignores invalid
values and a vanished folder.

## Files

Changed: `gui/app.py`, `gui/model.py` (+151), `test/test_emtk_trace_browser_t1.py` (the Setup tests start from the Setup
page; placeholder assertions removed). New: `gui/trace_browser_emtk.view.json` (every section, button and column has a
`description`), `test/test_emtk_trace_browser_t2.py` (31 tests). No manifest, guide, help, docs, `widget.py` or `core/` change.

## Tests

```
$ python -m pytest chisurf/plugins/tttr/trace_browser -q -p no:cacheprovider
81 passed, 5 skipped in 22.52s       (re-run by the reviewer; the 5 skips are the T3 legacy-engine trace tests)
```

The 31 new tests (hermetic via `conftest.py`, temporary copies of `BH_SPC132.spc` / `BH_SPC630_256.spc`): spec keys; the page
draws empty and populated at both sizes; real `.spc` files listed with the default image probe; Open -> folder dialog;
rating and notes edits persist to the metadata file, the rows, a rescan and a fresh app; invalid ratings (4, 9, 2.5, `abc`)
refused; edits refused while busy; the filter for all five entries; include-subfolders rescans; selection sets no trace;
Clear and Clear caches; drops (folder, file, missing path, empty); Select setup / Continue round trip; start page; settings
round trip; tooltips (recorder plus a spec walk); Qt-free; the Qt `TraceBrowser` and the app list the same rows for 5
filters x subfolders on/off; `list_files` unused. Deliberate breakage (`edit_cell` without `set_rating`,
`set_include_subfolders` without the rescan) failed 6 tests; restored.

## Evidence (`T2/`)

`after`: 28 controls, 0 without tooltip, Qt-free. `compare` exit 0: `lost` `[]`, `stale_explanations` `[]`, 104 explained
(T1's entries minus the 14 now drawn; Setup-page-only controls; later-card controls with "card T4"; the four closed
filter entries with "3-star widget -> 0..3 integer column (emtk data_table has no choice cell)"). The evidence run opens on
the Browser page because a last used setup exists (a copy of `~/.chisurf/detector_setups.json` in a temp settings folder);
without a saved setup `make_app()` opens on the Setup page. Screenshots read at full size (empty, populated, 800x600,
filtered, subfolders, dialog, file drop ignored, invalid rating): nothing overlaps or is clipped; Notes are cut at 800 wide
(full text in the cell tooltip).

## Findings and open points

1. `SnapshotJob.poll` copies every attribute back, so a change made while a job runs would be overwritten; mitigated by
   greying controls, refusing table edits while busy and queueing requests. Shared code untouched.
2. The Qt browser selects the first row after a scan and plots it, and precomputes all traces; the emtk table starts
   without a selection and precomputes nothing (T3 decides).
3. `model.status_text` was only set by `scan`; `apply_filter` now updates it.
4. `data_table` has no choice cell (a rating is a validated integer cell: double click, type, Enter) and `selected_call`
   reports one row. For T4 (Export selected, Delete) the table's multi-row selection exists in emtk
   (`DataTable.selected_key` plus `also_selected`, filled by Select All) and is readable through the form state's bound table
   (`FormState.tables[<source>]`); Ctrl/Shift-click range selection does not exist and is an emtk feature request if T4 needs it.

## Open (later cards)

T3: plot, annotation, y-range and bin-window effects, precompute, the five skipped tests, first-row selection, and the
Qt-free binner in `core/`. T4: Export / CSV / DOCX / Delete / hand-offs, Help / Guide, `entrypoints.emtk`, docs.

## Review (reviewer, 2026-10-01)

Verified, not taken from the hand-over: commits touch only trace_browser files, `T2/` evidence and the agent's log hunk;
81 passed / 5 skipped; the real MMFDB file is untouched by the run; `compare` exit 0 with `lost` `[]`; no Qt imports in
`gui/app.py` / `gui/model.py`; populated screenshot read next to `before_populated.png` (same files, same ratings model,
three stars confirm 0..3). The rating-range correction was made on the reviewer's request after checking `widget.py`.
**Accepted.**
