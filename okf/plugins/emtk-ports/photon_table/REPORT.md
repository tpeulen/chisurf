# emtk port report — `photon_table` (swap-candidate verification and upgrade)

Agent: claude (Sonnet), 2026-10-01, per `UPGRADE_BRIEF.md`. Board entry `T-20261001-SWAP4`. Verdict: **accept** after the upgrade; the
pre-upgrade app had one **REGRESSION** against the Qt tool (below), fixed in the plugin's own app.

Commits: `60bb3a5f5` Qt baseline and current emtk state (with `pre-upgrade/`), `0ad96ee1f` emtk app at parity (code, tests), then the evidence commit.

## 0. Pre-upgrade REGRESSION (the app opened by default was worse than the Qt tool)

The standalone app (`gui/controller.py:create_app`) failed three checks; reproduction of the first, from the repository root:

```
export QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD:$HOME/dev/emtk"
python okf/plugins/emtk-ports/photon_table/scripts/capture_emtk_before.py "$(mktemp -d)" /tmp/out   # loads a sample, then a missing path
# open /tmp/out/before_emtk_error_1200x800.png: the whole window is replaced by one line "Could not open ...: file does not exist"
# the "Load error" window has no close button and `error` is never cleared: the table, the controls and Open are unreachable for good
```

1. A failed load covered the window with an undismissable error box (Qt: a status line; the old table stays). Evidence `before_emtk_error_1200x800.png` against `before_populated_error.png`.
2. A dropped file did nothing: the drop hook sat on the controller, not on the app (`ImApp` calls `files_dropped` / `on_files_dropped`), although the tooltip and the empty-state text promise it.
3. No status line (Qt: "N photons from path"), no `export_settings` / `restore_settings` (the manifest declares `rows_per_page`, `input_file`), emoji labels (rule 6), the table hand-drawn (rule 4), a guide without `await` steps.

## 1. State at start

`git status --short chisurf/plugins/tttr/photon_table`: `?? chisurf/plugins/tttr/photon_table/` (the whole plugin was untracked: earlier migration stream, 2026-09-28; newest file `gui/app.py` 09-28 14:27, nothing modified in the last 60 minutes by anyone else; the shared index held no foreign staged file). `pre-upgrade/` holds `gui/app.py`, `gui/controller.py`, `manifest.json`, `tests/test_photon_table.py`.

## 2. Checklist of every control of the Qt tool (a Qt dock window hosting one emtk canvas; `before.json` is empty, so the hand compare is `compare_populated.json`)

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Open TTTR... (file dialog, TTTR filter) | spec button `request_open`, `FileDialog` (starts in the last file's folder) | yes |
| 2 | Drop a file on the window | `files_dropped` / `on_files_dropped` | yes (was broken) |
| 3 | Copy visible (TSV on the clipboard) | spec button `request_copy` (greyed with nothing loaded; Qt copied a header-only text) | yes, see 5 |
| 4 | Guide / Help | buttons drawn by `gui/app.py` | yes |
| 5 | File name, "N photons, T s, M µ-channels", "Routing channels: ..." | spec `info` sections | yes |
| 6 | Empty-state hint | spec `info` hidden once loaded | yes |
| 7 | First, Prev, Next, Last + "photons a-b" | spec button row + `info` | yes |
| 8 | First photon field (clamped) | spec `value` int with `call: set_first` | yes |
| 9 | Rows field (1-20000, clamped) | spec `value` int with `call: set_rows` | yes |
| 10 | Channel combo (All channels + used channels) | spec `choice`, `options_source: channel_labels` | yes |
| 11 | Table Photon / File idx / Channel / Micro time / Macro time [ms] | `data_table` (gained: sort, column picker, row status) | yes |
| 12 | "No photons loaded." | empty table with "0 rows x 5 columns", no rows | yes |
| 13 | Status bar: "N photons from path" / "Could not open path: error" | spec `info` `status_text` | yes |
| 14 | Dock headers closable / reopenable | `DockManager` windows `closable=True` | yes |
| 15 | Window geometry remembered | host's job (the emtk window) | n/a |

Screenshots: `before.png`, `before_populated.png`, `before_populated_{empty,filtered,page,error}.png`, `before_emtk_{empty,populated,error}_1200x800.png`.

## 3. Files

| File | New / changed | Purpose |
|---|---|---|
| `gui/model.py` | new | Qt-free `PhotonTableViewModel` over the unchanged core `PhotonTableModel` |
| `gui/photon_table_emtk.view.json` | new | panels `file` and `photons` |
| `gui/app.py` | rewritten | `PhotonTableApp`, `make_app` (SnapshotJob load, dialog, drop, Help/Guide, settings) |
| `gui/qt_host_app.py` | renamed from the old `gui/app.py` | the Qt tool's canvas, untouched; `tool.py` import changed only |
| `gui/controller.py` | removed | replaced by `make_app` (kept in `pre-upgrade/`) |
| `gui/guide.json`, `gui/help.md` | rewritten | 6 steps (4 await), help without raw Markdown marks |
| `tests/test_emtk_photon_table_parity.py` | new | 31 tests |
| `tests/test_photon_table.py` | one test updated | the Qt-free factory test now imports `make_app` (the controller is gone) |
| `manifest.json` | changed | `entrypoints.emtk` -> `gui.app:make_app` |

## 4. Automated evidence

```
compare: {"lost": [], "untooltipped": []}  qt-free: True  exit=0   (explained {}, stale_explanations [], gained 24)
after: 24 controls, 0 without tooltip, qt-free=yes
$ python -m pytest chisurf/plugins/tttr/photon_table -q -p no:cacheprovider
44 passed in 8.91s          (13 existing -> 13 + 31 new; 1 existing test edited)
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
13 passed in 26.23s
$ grep -rn "qtpy|PyQt|PySide|chisurf.gui" gui/app.py gui/model.py core/model.py   -> no match
```

The stock `compare` is vacuous here (`before.json` has 0 controls: the Qt tool is one canvas), so `scripts/compare_populated.py` inventories the Qt tool's hosted app and the native app with the same file loaded (`compare_populated.json`): the same controls, `qt_only` is only `first_photon` / `channel_filter` (the field ids; the channel combo is drawn by the form's own combo, which the recorder does not list, and it is tested), no untooltipped control on either side.

## 5. Deliberate differences

| Item | Why |
|---|---|
| Copy visible is greyed with nothing loaded | Qt copied a header-only text; nothing to copy |
| A missing path says "file does not exist" | tttrlib's message for it ("unsupported container type") misleads; an existing unreadable file keeps tttrlib's text, equal to the Qt status message (tested) |
| Photon / File idx without thousands separators | the table formats printf-style; values are equal (tested) |
| Table sortable per page, column picker | gained |
| Open dialog filter lists .ptu .phu .ht2 .ht3 .pt3 .t3r only (as Qt); .spc needs "All files" or a drop | parity kept |
| `channel_filter` is not remembered | a load resets it, as in Qt; `rows_per_page` and `input_file` are (the file is not reopened) |

## 6. Tests

31 new tests (`tests/test_emtk_photon_table_parity.py`, hermetic: temp `CHISURF_SETTINGS_DIR`, private copy of `test/data/tttr/BH/132/BH_SPC132.spc`, 183,657 photons, channels 0/1/8/9):

| Required test | Test | Asserts |
|---|---|---|
| 1 model reference result | `test_rows_equal_tttrlib_for_the_same_file`, `test_filtered_rows_equal_tttrlib`, `test_summary_and_cells_equal_the_qt_tool` | every row's idx/channel/micro/macro equals tttrlib's arrays; the filtered rows and renumbering; the Qt tool's drawn summary, cells and status text equal the native ones |
| 2 actions and errors | `test_navigation_*`, `test_the_fields_clamp_*`, `test_the_channel_filter_*`, `test_load_resets_*`, `test_a_second_load_is_refused_*`, `test_copy_*`, `test_open_shows_the_file_dialog_*` (load and cancel), `test_a_dropped_file_is_opened`, `test_a_missing_file_*`, `test_an_unreadable_file_keeps_the_old_table_*`, `test_the_error_does_not_cover_the_window` | each button and field and its error path |
| 3 spec keys exist | `test_every_spec_key_exists_on_the_model` | attr/call/source/actions/hidden_when/columns |
| 4 draws | `test_draws_empty_and_populated_at_both_sizes[3 sizes]`, `test_the_empty_state_is_a_message_and_no_rows` | 1200x800, 800x600, 500x500; no invented rows |
| 5 main action | `test_load_resets_the_view_and_remembers_the_file` | load -> status -> view reset |
| 6 Qt-free | `test_port_is_qt_free` | `qt_free("photon_table")` |
| 7 tooltips | `test_every_control_has_a_tooltip`, `test_the_populated_app_has_no_untooltipped_control_either` | inventory + spec walk incl. columns |
| 8 persistence | `test_settings_round_trip` | export/restore, clamp |
| also | guide targets drawn + awaits, tour hears actions, help draws, manifest entry | |

Deliberate breakage (restored afterwards): `go_last` off by one and `set_rows` without the 20000 cap.

| Test | What I broke | Result when broken |
|---|---|---|
| `test_navigation_buttons_page_through_the_file` | `go_last` clamped `count - rows - 1` | `assert 183456 == (183657 - 200)` |
| `test_the_fields_clamp_like_the_qt_tool` | `set_rows` without the cap | `assert (1000000 == 20000)` |

Pre-existing failures: none.

## 7. Screenshots I looked at (full size)

| File | Observation |
|---|---|
| `after_populated_1200x800.png`, `_800x600.png` | summary, status, Open/Copy/Guide/Help, nav row, three fields, 200-row table with status line; same first rows as `before_populated.png` (0.768366 ms ...); nothing clipped |
| `after_populated_filtered_*.png` | channel 9: Photon renumbered 0.., File idx 0, 16, 19, ... equals the Qt filtered page in `before_populated.json` |
| `after_populated_page_1200x800.png` | photons 100-150, equals `before_populated_page.png` row for row |
| `after_populated_error_{missing,unreadable}_1200x800.png` | error text in the status area, table and controls intact (the regression of section 0 is gone) |
| `after_empty_*.png` | hint text, greyed Copy and nav, empty table, no invented rows |
| `after_populated_file_dialog`, `_help`, `_guide`, `_narrow_500x500` | dialog is emtk's full-window one; help readable; tour spotlights Open; narrow keeps all labels (table headers elide) |

None shows a clipped label, overlapping windows, an empty panel or an oversized status box. In the tour card the hint's emoji glyph draws as a blob: emtk/shared `help_guide.py`, not this plugin.

## 8. Workflow

Open TTTR... (or drop) -> `load_path` on a SnapshotJob -> status "183,657 photons from <path>" -> Next / Prev / Last, fields, channel -> Copy visible. Data: `test/data/tttr/BH/132/BH_SPC132.spc`.

## 9. Persistence, guide, help, docs

`export_settings`: `rows_per_page`, `input_file` (the manifest's schema; the Qt tool remembered only window geometry). Guide 6 steps, awaits on `request_open`, `go_next`, `channel_filter`, `request_copy` (tested to be drawn and heard). Help has no links. Docs: no `docs/` page for this tool exists (only passing mentions in the H2MM and PDA guides): **docs gap**, not added.

## 10. Blocked / open

none for the plugin. Open for the reviewer: remove `photon_table` from `emtk_preview.json` after accepting (not touched). Screenshots take 5-17 s each on `PixelPainter`.
