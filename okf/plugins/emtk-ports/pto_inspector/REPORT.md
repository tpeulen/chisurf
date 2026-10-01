# emtk port report — `pto_inspector` (swap-candidate verification and upgrade)

Agent: claude (Sonnet), 2026-10-01, per `UPGRADE_BRIEF.md`. Board entry `T-20261001-SWAP4`. Verdict: **accept** after the upgrade; the
pre-upgrade app had a **REGRESSION** against the Qt tool (below), fixed in the plugin's own app.

Commits: `ecfb4716a` Qt baseline and current emtk state (with `pre-upgrade/`; it also holds the first `after`/`compare` run of the
pre-upgrade app, overwritten later), `d457baccd` emtk app at parity with the Qt tool, the follow-up "object table widths, no stale notice..."
commit, then the evidence commit.

## 0. Pre-upgrade REGRESSION: a dropped container never reached the app

The Qt window opens a `.pto` dropped on it (`PtoInspectorTool.on_paths_dropped`). The native window did not take the drop. Reproduction (repository root):

```
export QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD:$HOME/dev/emtk"
python okf/plugins/emtk-ports/pto_inspector/scripts/capture_emtk_before.py "$(mktemp -d)" /tmp/out
# prints {"host_would_accept_a_drop": false, ...}: emtk's Qt host (emtk/qt_host.py dragEnterEvent, used by ChiSurf's registry for every
# entrypoints.emtk plugin) accepts a drag only when the control has `files_dropped` or `on_files_dropped`; the app only had
# `on_paths_dropped`, so the drag was refused and the tool's documented route (drop a .pto, or drop a vendor file to pack it) did nothing.
```

Also: the guide was built to wait for nothing (`wait_for_controls` off) and its hints named the Qt buttons ("📂 Browse", "🔍 Verify"); the help window showed
the Qt Markdown marks raw and Qt labels; with no container the Data and Curve windows claimed "The selected artifact is not a table / a curve";
a multi-line verify verdict did not fit the one-line status.

## 1. State at start

`git status --short chisurf/plugins/core/pto_inspector`: ` M manifest.json`, `?? gui/app.py`, `?? gui/translations.py`, `?? test/test_native.py` (earlier migration stream,
2026-09-28/29; nothing modified in the last 60 minutes by anyone else, no foreign staged file). `pre-upgrade/` holds the three files and the manifest diff.

## 2. Checklist of every control of the Qt tool

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Toolbar Open (file dialog, .pto filter) | button `Open`, `FileDialog` (also lists vendor files, to pack) | yes |
| 2 | Toolbar Reload | `Reload` (greyed with nothing open) | yes |
| 3 | Toolbar Verify (message box with the verdict) | `Verify` -> verdict in the status line (mismatches joined to one line) | yes |
| 4 | Toolbar Open tool (enabled when a tool claims the step; picker when several) | `Open tool` + tool combo in the Provenance window | yes |
| 5 | Toolbar Export (CSV for a table, raw extract otherwise) | `Export` + save dialog | yes |
| 6 | Guide / ? | `Guide`, `Help` | yes |
| 7 | Container path + browse + MMFDB button | path line, `Open`, `Database` (DatasetPicker) | yes |
| 8 | Drop a .pto / a vendor file (packing offer, `tttr_to_pto` guard) | `files_dropped`; pack dialog (folder choice, source kept, no overwrite) | yes (was broken) |
| 9 | Summary (file, size, profile, container, dictionary, objects, kinds, integrity) | same text, tags removed | yes |
| 10 | Objects table (Name, Kind, Operation, Grain, Rows, Size, parents), selection, double click opens the tool | `TableBinding` table with the same columns, filter, column picker | yes |
| 11 | Provenance graph, node click selects, double click opens the tool | `GraphControl`, same | yes |
| 12 | Data table with the stored units in the headers, search | payload table, units in the headers, filter | yes |
| 13 | Curve with units and log x for a correlation | `implot` line, same axes | yes |
| 14 | Details and Lineage | Details / Lineage tabs (gained: Parameters, Text) | yes |
| 15 | Status bar "name - N objects" / "Cannot open ..." | status window | yes |
| 16 | Message boxes: Integrity, Exported, No tool for this step | status-line notices | yes (deliberate, see 5) |

Screenshots: `before.png`, `before_populated*.png` (empty, populated, lifetimes, fcs, verified, error), `before_emtk_*_1300x850.png`.

## 3. Files

| File | New / changed | Purpose |
|---|---|---|
| `gui/app.py` | changed | host drop hook (`files_dropped`/`on_files_dropped`), tour waits for Open and Verify, no-container wording, one-line verify verdict, narrower object columns and a wider left window |
| `gui/guide_emtk.json`, `gui/help_emtk.md` | new | native guide (8 steps, 2 awaits) and help (no Markdown marks, links to the two docs pages); the Qt tool keeps `guide.json` / `help.md` |
| `gui/translations.py` | changed | the new strings in de/fr/es/pt/ru |
| `test/test_emtk_pto_inspector_parity.py` | new | 31 tests |

Not rewritten as a `*_emtk.view.json`: the app is six-language (`translations.py`), `emtk.view_form` has no translation hook, so a spec would drop the
languages; its table is already the emtk table machinery (`TableBinding`) and the rest is a graph, a plot and prose that a spec cannot express. Reported as a deliberate choice.

## 4. Automated evidence

```
compare: lost []  untooltipped []  qt-free: True  exit=0   (explained 2, stale_explanations [])
after: 32 controls, 0 without tooltip, qt-free=yes
$ python -m pytest chisurf/plugins/core/pto_inspector -q -p no:cacheprovider
81 passed in 39.35s        (50 existing + 31 new)
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider    (not rerun for this plugin; unchanged tool)
```

## 5. Deliberate differences (`deliberate.json`)

`?` (the Help button is labelled), `0rows x 0columns` (the Qt data table's count line for an empty payload; the emtk Data window says why it is empty). Behaviour:
Qt message boxes (Integrity, Exported, No tool for this step) are status-line notices; a ported tool opens inside the window (a "Back to inspector" bar) while an
unported one says so; gained: Database, Fit graph, Parameters and Text tabs, table filter and column picker.

## 6. Tests

| Required test | Test | Asserts |
|---|---|---|
| 1 reference result | `test_rows_equal_the_container_and_the_qt_table`, `test_payload_and_curve_equal_what_was_stored`, `test_the_details_name_the_settings_and_the_parents` | rows equal `Measurement.artifacts()` and every cell of the Qt table; summary, details and status equal the Qt tool's; payload and curve equal the stored arrays (linspace/logspace), units in headers, log x |
| 2 actions and errors | selection by row / node / double click; verify equal to the Qt message, damaged container, nothing open; export of a table and a raw payload byte-equal to the Qt tool's files; nothing selected; open tool picks the same manifest as Qt, none claims it, ported / unported tool; broken file equals the Qt status; reload; open dialog and cancel; MMFDB picker | each action and error path |
| 3 drop / pack | host hook, vendor drop -> pack dialog -> container written, sources kept, overwrite refused | |
| 4 draws | `test_draws_empty_and_populated[3 sizes]`, curve and table draw | 1200x800, 800x600, 500x500; empty state says "No container open" |
| 6 Qt-free | `test_port_is_qt_free` | |
| 7 tooltips | `test_every_control_has_a_tooltip`, enabled states follow the state | empty and populated inventory |
| 8 persistence | `test_settings_round_trip`, new strings in five locales | filename, selection, filter; a vanished file is reported |
| also | guide targets drawn, tour waits for Open and Verify, Qt tool keeps its guide/help, help links live | |

Deliberate breakage (restored): the drop hook returning `False` and the verify verdict left multi-line: `test_the_host_hook_takes_a_dropped_container`,
`test_a_dropped_vendor_file_is_offered_for_packing_and_sources_are_kept` and `test_a_damaged_container_fails_verification_in_one_status_line` failed; restored, 81 passed.

Pre-existing failures: none.

## 7. Screenshots I looked at (full size)

`after_populated_1200x800.png` (all six objects, columns readable, graph with README / m.ptu / bursts / background / lifetimes / fcs, Data with `x [milliseconds]`
and `y [dimensionless]`, Curve log x, Details), `_800x600` (header names elide, still readable), `after_populated_lifetimes` (table payload, "not a curve"),
`after_populated_verified` (integrity row and verdict in the status line), `after_populated_pack_dialog`, `after_populated_error` ("No container open" in every window),
`after_empty`, `after_populated_help`, `after_populated_guide` (spotlight on the path, hint fits), `after_populated_narrow_500x500`. In the first pack-dialog shot the
previous Verify verdict showed inside the dialog; fixed (the notice is cleared when files are dropped) and re-shot. Nothing clipped or overlapping; the tour's hint glyph is a blob (shared emtk font).

## 8. Workflow

Drop (or Open) `m.pto` -> last result selected -> click a row -> graph, data, curve and details follow -> Verify -> Export -> Open tool. Data: a private copy of
`test/data/clsm/Leica_SP5.ptu` packed by the plugin's own fixture with burst, background, lifetime and FCS results.

## 9. Persistence, guide, help, docs

`export_settings`: `filename`, `selected_uid`, `artifact_filter` (the Qt tool remembered window geometry only). Guide: 8 steps, awaits `filename` (heard when a container opens, by any route) and `Verify`.
Help links: two docs pages, tested live. Docs: `docs/guides/63_pto_inspector.md` exists and is unchanged (the Qt tool is unchanged).

## 10. Blocked / open

none for the plugin; `emtk_preview.json` untouched (reviewer removes `pto_inspector` after accepting). Gap for emtk: no translation hook in `view_form` (why this app is not a spec).
