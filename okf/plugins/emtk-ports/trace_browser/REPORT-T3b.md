# trace_browser, card T3b: trace plot, annotation and precompute

Implementing agent (Sonnet), 2026-10-01. Code and tests: commit `fd040fd96` ("trace_browser T3b: trace plot, annotation and
precompute in the emtk app"); evidence, this report and the log: the second commit "trace_browser T3b: evidence and report".
Board claim `T-20261001-TB3b`. Card T3b of 5 (T0 model, T1 Setup, T2 Browser, T3a binner, **T3b plot**, T4 export / hand-off / guide /
manifest). The manifest is not switched; the card is checked with `--entry chisurf.plugins.tttr.trace_browser.gui.app:make_app`.
State at start: `git status --short -- chisurf/plugins/tttr/trace_browser` printed nothing.

## What the trace area does

The right window "Trace plot" (was a placeholder) now shows, for the **current file** (the selected row):

* a header line: `m001.spc | 10 ms bins | 6233 bins`, or `Loading m001.spc…` while a load runs, or the error text;
* `emtk.implot` subplot of one row, two columns, y axes linked: the **trace plot** (`Time (s)`, `Counts / <bin> ms`, legend) and,
  right of it, the **counts histogram** (`Counts (log)`, log10 x axis; x = how many time bins hold a count, y = the count, as the Qt
  plot draws it: positive bins only, 100 histogram bins). One coloured line per series: `green`, `red`, `yellow` keep their own
  colour, any other label takes a fixed 6-colour palette, plus the **`Sum`** series the Qt plot also ends with (grey, drawn first so
  it stays behind the detectors). **Overlaid**, not stacked (the card allowed either; the Qt plot stacks one row per series; with the
  same y range on every row an overlay with a legend shows the same data in one plot);
* the **y range** comes from the form's `Y min` / `Y max` (`model.y_range`, ordered low/high, so a swapped entry is swapped as in Qt).
  Read of the Qt tool: it applies the two spin boxes **always** (defaults 0 / 1000), there is no "0 means auto". Here equal limits
  mean "fit the data" (an emtk-only reading, since a zero-height axis is useless); every other value is a fixed range. The range is
  applied with `COND_ALWAYS` only on the frame a limit, the file or the bin window changed, otherwise `COND_ONCE`, so zooming and
  panning with the mouse is not undone every frame;
* **decimation** (display only): `decimate_minmax` keeps the minimum and the maximum of each of `MAX_POINTS // 2` runs of bins when a
  series has more than 4000 points; the model keeps all bins (62329 at 1 ms). The decimated lines and histograms are built once per
  loaded trace (`TraceView`), not per frame;
* the **annotation** box (`im.input_text_multiline`, 90 px) under the plot. No empty state curve: with no file the area says "Open a
  folder with TTTR files, then select a file to show its trace." / "Select a file in the table to show its intensity trace." / "No
  file is listed, so there is no trace to show." and the annotation box is replaced by "Select a file to write an annotation for it.".

### Loading (a `SnapshotJob`, declarative)

`_pump_trace` runs every frame: it wants `(current file, window_ms)` and loads it on `self.load_job` (a `SnapshotJob`) whenever the
model's `trace` is another `(file, window)`, one load at a time. A row click (`selected_call` -> `model.select_row`), a changed bin
window, the first-row selection after a scan and a finished older load therefore all end in the right trace without knowing about each
other; while a changed window loads, the old trace of the same file stays visible under the `Loading…` line. A failed load puts
`Failed to load <file>: <error>` into `model.trace_error` (plot header and status line), draws nothing and is **not retried every
frame** (the failed `(file, window)` is remembered until another file, window or scan). Cache and metadata behaviour is the
model's, unchanged (`model.load_trace` -> RPC client -> `core.trace.load_trace` with the in-memory and on-disk cache).

**Important design point (a defect avoided).** `SnapshotJob` copies the model and writes *every attribute* of the copy back when the
work ends. A trace load or a precompute may last long, so running them on a snapshot **of the model** would overwrite whatever the user
changed meanwhile (a rating, a note, the selection). The two jobs therefore run on a small helper (`_TraceTask`, holds the real model,
nothing else) and the model's own `trace` is set by the draw loop (`model.set_trace`). A test sets a rating and a note while a
precompute runs and checks both survive. The existing scan job (T2) still copies the model; its known caveat (T2 finding 1) is
unchanged.

### First-row selection

The Qt browser selects the first row after every scan and plots it, or clears the plot when nothing is listed. `model.scan()` now does
the same: `select_row(rows[0])` (or clears selection, current file and trace when there are no rows) and sets `precompute_pending`.
The table highlight follows the model (`_sync_table_selection`: `DataTable.select_key`, which does not fire `selected_call` again). A
filter that hides the shown file clears it, as the Qt plot cleared when its selected row disappeared (`apply_filter`). **T2 tests
changed accordingly** (explained below).

### Annotation (the same field as the Notes column)

The box shows `model.get_notes(current_file)` and writes every edit with `model.set_notes(path, text, flush=False)`: the model's
row dicts are the table's records, so the Notes cell updates in the next frame, and a Notes-cell edit (`edit_cell` -> `set_notes`) is
what the box shows next frame. **Saving is debounced like Qt (300 ms)**: the metadata file is written 0.3 s after the last edit, at
once when another file is selected, when a scan runs (`model.busy`), and in `app.close()` (tests for each). Typing works through the
real keyboard path (click into the box, text events; test) not only through a stub. The box is disabled while a scan runs.

### Precompute (visible background job)

The Qt tool precomputed every listed file after **every scan**, synchronously, behind a modal progress dialog. Here:

* `model.precompute_after_scan` (default **on**, as Qt; a new toggle `Precompute after scan`, remembered in the settings) sets
  `precompute_pending` after a scan;
* two buttons `Precompute` (run now, with the current bin window) and `Stop` (greyed unless a precompute runs);
* the job is `model.run_precompute()` (wraps the unchanged `precompute_all_traces(progress)`; progress and cancel live in the dict
  `model.precompute`) on its own `SnapshotJob`; the status line shows `Precomputing traces 3/4: m002.spc` while it runs and then
  `Precomputed 4 trace(s).`, `No traces to compute (all cached).` or `Precompute stopped after N trace(s).`;
* **a new scan cancels a running precompute** (the app sets the cancel flag when it starts a queued scan), and a pending precompute
  waits until the scan and the previous precompute are done. No modal dialog.

## Files

Changed: `gui/app.py` (+457), `gui/model.py` (+147: `trace_error`, `precompute*`, `set_trace`, `fail_trace`, first-row selection in
`scan`, hidden-file clearing in `apply_filter`, `enabled` per control, `background_text`), `gui/trace_browser_emtk.view.json`
(a button row `Precompute` / `Stop`, the toggle, bin-window tooltip), the two earlier test files (below). New:
`test/test_emtk_trace_browser_t3b.py` (29 tests). No manifest, guide, help, docs, `widget.py`, `core/` or emtk change.

Changes to T1/T2 tests (all explained by this card): the placeholder string `Trace plot: card T3` is now the annotation empty-state text;
the spec walk counts changed (8 attrs, 6 actions, 16 described items: the new button row, toggle); the T2 `make_app()` helper switches
`precompute_after_scan` off (those tests are about the page); T2's `settle()` also waits for the load and precompute jobs; the T2
"selecting a row ... and computes no trace" test became "sets selection and current file" (the first row is now selected after a scan
and a selection now loads a trace); `cache.mkdir(exist_ok=True)` because the first row's trace creates the cache folder.

## Tests

```
$ python -m pytest chisurf/plugins/tttr/trace_browser -q -p no:cacheprovider
129 passed, 6 warnings in 52.00s      (100 before + 29 new; the warnings are pyqtgraph's stepMode deprecation in the Qt side-by-side test)
$ python -m pytest chisurf/plugins/tttr/trace_browser/test/test_emtk_trace_browser_t3b.py -q -p no:cacheprovider
29 passed, 6 warnings in 23.51s
$ python -m pytest test/gui/test_emtk_port_parity.py test/test_prd_mentions.py -q -p no:cacheprovider
1 failed, 14 passed in 33.34s
```
The one failure is pre-existing and not this card's: `test_prd_mention_allowlist_has_no_stale_entries` lists
`chisurf/plugins/calculator/kappa2_dist/gui/tool.py` and `chisurf/plugins/tttr/tttr_time_windows/tests/test_construction_smoke.py`
(other plugins; no trace_browser file names a PRD). The real `~/.chisurf/flr/sample_management.db` and `detector_setups.json` mtimes
did not change over the runs (`stat` before/after).

The 29 new tests (hermetic via conftest, temporary copies of `BH_SPC132.spc` only): selecting a row loads and draws (the drawn lines
are `Sum`, `green`, `red`, `yellow`; 6233 bins; sums [22443, 56257, 0] and 78700 for Sum; histogram has no yellow line; drawn y values
a subset keeping the series' min and max; the "Loading m001.spc…" state is seen); with decimation switched off the drawn y arrays equal
the model's counts exactly and the sums are [22443, 56257, 0]; a changed bin window reloads (1 ms: 62329 bins, same sums, `1 ms bins`
and `Counts / 1 ms` drawn, back to 10 ms); y range applied to both y axes (0..1000 default, 5..300 with `COND_ALWAYS` once and `COND_ONCE`
after, swapped entries ordered, equal limits give auto-fit and no fixed limits); decimation unit test (burst and dip survive, every
column keeps both extremes, a short trace is untouched) and the model keeps 62329 bins while at most 4000 points are drawn;
annotation: edit persists to the file after the debounce, appears in the table Notes cell, survives a rescan and a fresh app; the
reverse (Notes cell edit shows in the box and the file); typing through the real keyboard path; the box follows the selected file and
flushes on a switch; closing flushes; empty state (no curve drawn: no `plot_line`, no `begin_plot`); no selection; load error from an
unreadable file and from a raising model, no retry loop, cleared by another selection; first-row selection (model, table highlight,
trace, empty folder clears); a filter hiding the shown file clears the plot; precompute after a scan reports `Precomputing traces i/N:
file` then `Precomputed 6 trace(s)` with the cache files on disk, Stop cancels (`stopped after n`, 1 <= n < 5), a new scan cancels,
a rating and a note set while it runs are kept and saved, the headless model methods; the page draws populated at 1200x800 and 800x600
with every label; tooltips (`emtk_inventory`: `controls_without_tooltip == []`, empty and populated, plus a spec walk and a source
check of the two hand-drawn tooltips); every spec action exists on the model; Qt-free proof
(`qt_free("trace_browser", ENTRY)`); settings round trip of the new toggle; the Qt `TraceBrowser` and the emtk app draw the same series
for the same file (labels `green, red, yellow, Sum` and per-series sums equal, read from the pyqtgraph data items).

**Deliberate breakage**, made once and restored (final run green): (1) `decimate_minmax` keeping only the maximum of each column, (2)
`shown_trace` reporting the *wanted* window (so a bin-window change never reloads) and (3) `scan` no longer selecting the first row.
Together they failed 19 tests (among them the decimation tests, `test_a_changed_bin_window_loads_the_trace_again`,
`test_a_scan_selects_the_first_row_and_plots_it`, and the annotation, load-error and populated-draw tests that depend on the first
row); with the files restored `git status` is clean and 129 pass.

## Evidence (`okf/plugins/emtk-ports/trace_browser/T3b/`)

```
$ CHISURF_SETTINGS_DIR=<tmp> MMFDB_SETTINGS_DIR=<tmp> MMFDB_DATABASE_PATH=<tmp>/mmfdb_test.db \
  python -m test.gui.emtk_port_parity after trace_browser --out okf/plugins/emtk-ports/trace_browser/T3b --entry chisurf.plugins.tttr.trace_browser.gui.app:make_app
after: 29 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/trace_browser/T3b
$ python -m test.gui.emtk_port_parity compare trace_browser --out okf/plugins/emtk-ports/trace_browser/T3b
{"lost": [], "untooltipped": []}
qt-free: True            exit=0
```
`compare.json`: `lost` [], `stale_explanations` [], 104 explained, 15 gained (the Trace plot window, `Precompute`, `Stop`, `Precompute after
scan`, the annotation box and their empty-state texts), 118 before / 29 after. `before.json` is a byte copy of T2's; `deliberate.json`
is T2's **unchanged**: none of its 104 entries was explained by a control this card draws (the Qt baseline has no label for the
plot or the annotation, whose placeholder is not a control), later-card controls keep their "card T4" reason. The evidence run used a
temporary settings folder holding a copy of the saved `detector_setups.json` (so the app opens on the Browser page with the real
"ALEX Suite (auto)" setup); `~/.chisurf` was only read.

Screenshots (all read at full size): `after_1200x800.png` (empty state), `after_800x600.png` (empty, 800x600),
`after_populated_1200x800.png` / `after_populated_800x600.png` (4 copies of `BH_SPC132.spc`, `m001.spc` selected, ratings 3/1,
annotation typed with the keyboard, Notes cell shows it; the trace of `m001.spc`: Sum grey, green, red, yellow all-zero, legend,
`Counts (log)` histogram), `after_loading_1200x800.png` (a deliberately slowed load: `Loading
m002.spc…`, no stale curve for the other file), `after_bin_window_1ms_1200x800.png` (1 ms, 62329 bins), `after_yrange_0_120_1200x800.png`
(y 0..120 on both axes, the histogram follows), `after_precompute_running_1200x800.png` (`Precomputing traces 3/4: m002.spc`, Stop
enabled, Precompute greyed), `after_load_error_1200x800.png` (an unreadable `.ptu`: the error in the status line and the plot area, no curve).
Nothing overlaps or is clipped; the Notes column is cut at 800 px width (full text in the cell tooltip, as in T2). Compared with
`before_populated.png`: same file table content and annotation, one plot instead of four stacked rows; the Qt y axis was always 0..1000 as here.

## Findings and open points

1. **`SnapshotJob` semantics**: it writes every attribute back, so long jobs on the model itself lose concurrent user edits.
   T2's scan job still has this (mitigated by greying controls). A future card or the reviewer may move the scan to the helper pattern
   too; shared `chisurf/emtk/jobs.py` is untouched.
2. Overlaid rather than stacked series (see above). A stacked variant is a layout change (`begin_subplots` with n rows) if the reviewer
   wants it; the `TraceView` data are the same.
3. `Precompute after scan` defaults on as in Qt; for a big folder it computes in the background (visible, stoppable) and competes
   with the foreground load only for the CPU.
4. A filter that hides the shown file now clears the current file and plot (Qt behaviour); the first row is *not* re-selected then.
5. The empty-limits reading (equal Y min / Y max = fit) is not in the Qt tool, which has no auto mode.
6. The annotation box's text-cursor is drawn even when the box is not focused (emtk's text editor); cosmetic.
7. Retry after a failed load only by selecting another file, changing the bin window or scanning (Clear caches does not retry).

## Open (T4)

Export, CSV, DOCX, Delete, Transfer to analysis, Time window, ndX, Help / Guide, `entrypoints.emtk`, docs, `guide.json`, `help.md`.
