# emtk port report — `tttr_to_pto` (swap-candidate verification and upgrade)

Agent: claude (Sonnet), 2026-10-01, per `UPGRADE_BRIEF.md`. Board entry `T-20261001-SWAP4`. Verdict: **accept** after the upgrade; the
pre-upgrade app had a **REGRESSION** against the Qt tool (below), fixed in the plugin's own app.

Commits: `aa3f8645b` Qt baseline and current emtk state (with `pre-upgrade/`), `f8c6d4469` emtk app at parity with the Qt tool, then the evidence commit.

## 0. Pre-upgrade REGRESSION: a drop could not reach the app

The Qt tool is one thing: a list you drop files on. The default-opened native app took no drop. Five-line reproduction (repository root):

```
export QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD:$HOME/dev/emtk"
python okf/plugins/emtk-ports/tttr_to_pto/scripts/capture_emtk_before.py "$(mktemp -d)" /tmp/out
# prints {"host_would_accept_a_drop": false, ...}: emtk's Qt host (emtk/qt_host.py dragEnterEvent) accepts a drag only when the control
# has `files_dropped` or `on_files_dropped`; the app only defined `on_paths_dropped` (the Qt tool's name), and the app had no other
# way to give it files (no Add button), so in the real window nothing could be converted. Tests passed because they called add_paths().
```

Also: history was drawn as hand-made text rows (rule 4), the guide steps had no `await` and were built in Python, `export_state`/`restore_state` were never called by the host (`chisurf/emtk/state.py` calls `export_settings`).

## 1. State at start

`git status --short chisurf/plugins/core/tttr_to_pto`: ` M manifest.json`, `?? gui/app.py`, `?? gui/strings.json`, `?? test/test_native.py` (earlier migration stream, 2026-09-27/29; nothing modified in the last 60 minutes by anyone else, no foreign staged file). `pre-upgrade/` holds the three files and the manifest diff.

## 2. Checklist of every control of the Qt tool

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Guide button | button `Guide` (guide_emtk.json, 5 steps, 1 await) | yes |
| 2 | ? help button | button `Help` (help_emtk.md) | yes (renamed) |
| 3 | Explanatory label | spec `info` | yes |
| 4 | Drop list: vendor files -> one .pto (name order, sidecar rides along) | `files_dropped` / `on_files_dropped`; table rows | yes (was broken) |
| 5 | Drop list: a .pto -> unpack | same | yes |
| 6 | List row text "a, b -> out" / "x: could not pack (err)" | table row: Status, Action, Files, Result | yes |
| 7 | Filter: lone .set refused, only vendor files and .pto accepted | `TttrToPtoModel.accepts`, rejected rows (Qt dropped them silently) | yes |
| 8 | List tooltip | spec description on the table + row tooltip with the full paths | yes |
| - | gained: Add files... (dialog), Clear history, status line, verification of every pack | | gained |

Screenshots: `before.png`, `before_populated_{empty,packed,unpacked,error}.png`, `before_emtk_{empty,packed,error}_900x600.png`.

## 3. Files

| File | New / changed | Purpose |
|---|---|---|
| `gui/model.py` | new | Qt-free `TttrToPtoModel` (queue, worker, rows as table records, settings) |
| `gui/tttr_to_pto_emtk.view.json` | new | hint, buttons, status, `data_table` |
| `gui/app.py` | rewritten | `TttrToPtoApp`, `create_app`/`make_app`, drop hook, Add dialog, Help/Guide |
| `gui/guide_emtk.json`, `gui/help_emtk.md` | new | the native tour and help (the Qt tool keeps `guide.json`/`help.md` untouched) |
| `gui/strings.json` | untouched, now unused | see section 5 |
| `test/test_emtk_tttr_to_pto_parity.py` | new | 26 tests |
| `test/test_native.py` | changed | `export_state` -> `export_settings`; two obsolete tests removed (translations, hand-drawn tooltip strings) |

## 4. Automated evidence

```
compare: lost []  untooltipped []  qt-free: True  exit=0   (explained 3, stale_explanations [])
after: 13 controls, 0 without tooltip, qt-free=yes
$ python -m pytest chisurf/plugins/core/tttr_to_pto -q -p no:cacheprovider
43 passed in 17.97s        (19 existing -> 17 kept + 26 new)
$ grep -rn "qtpy|PyQt|PySide|chisurf.gui" gui/app.py gui/model.py api.py   -> no match
```

## 5. Deliberate differences (`deliberate.json`)

`1` (the Qt list's row-number header), `?` (the Help button is labelled), the explanatory sentence (drawn wrapped over two strings). Behaviour: a rejected path is listed instead of being dropped silently; every pack is verified (as the earlier app already did); history is documentary and never replayed. **Translations**: the earlier app had a six-language catalog (`gui/strings.json`); emtk's `view_form` has no translation hook, so the spec texts are English. The Qt tool was English only. Open point for emtk (a hook that runs spec `label`/`description` through `i18n.tr`), not patched.

## 6. Tests

| Required test | Test | Asserts |
|---|---|---|
| 1 reference result | `test_pack_and_unpack_equal_the_qt_tool`, `test_an_unreadable_container_fails_with_the_text_the_qt_tool_shows`, `test_the_accept_rule_equals_the_qt_filter` | Qt tool and native app packed/unpacked the same input in two folders: same row text, same files, bytes equal the originals, containers verify; same error text; same accept rule |
| 2 actions and errors | pack keeps sources; failed verification; rejected sidecar / missing / unknown type; one at a time in order; clear history; host hook; drop converts; Add files dialog and cancel | each action and error path |
| 3 spec keys | `test_every_spec_key_exists_on_the_model` | attr/call/source/actions/columns/row key/tooltip key |
| 4 draws | empty state, `test_draws_empty_and_populated[4 sizes]` | 1200x800, 900x600, 800x600, 500x500; no invented rows |
| 5 end to end | `test_a_drop_through_the_hook_converts` | host hook -> file written -> Verified row |
| 6 Qt-free | `test_port_is_qt_free` | |
| 7 tooltips | `test_every_control_has_a_tooltip`, populated variant | inventory + spec walk incl. columns |
| 8 persistence | `test_settings_round_trip`, `test_restore_is_refused_while_a_write_runs` | history documentary, interrupted never replayed, last folder |
| also | guide targets drawn and awaits, tour hears `request_add`, help draws, Qt tool keeps its own help/guide, manifest entry | |

Deliberate breakage (restored): pack order reversed and the accept check disabled: 9 tests failed, e.g. `test_pack_and_unpack_equal_the_qt_tool`, `test_a_lone_sidecar_a_missing_file_and_an_unknown_type_are_rejected`, `test_the_host_hook_takes_a_drop`; restored, 43 passed.

Pre-existing failures: none.

## 7. Screenshots I looked at (full size)

`after_populated_900x600.png`, `_800x600.png` (four rows: Verified Pack, Verified Unpack, Failed with the tttrlib text, Rejected sidecar; status line; header buttons), `after_populated_packed_*`, `after_empty_*` (hint, empty table, no rows), `after_populated_narrow_500x500.png`, `after_populated_file_dialog_900x600.png`, `after_populated_help_900x600.png`, `after_populated_guide_900x600.png` (spotlight on Add files..., hint fits after I shortened it). The long error text is cut in the Result cell (the row tooltip has it whole). Nothing clipped, overlapping or empty-panel. The tour's hint glyph draws as a blob (shared `help_guide.py`/emtk font, not this plugin).

## 8. Workflow

Drop (or Add files...) `m000.spc`, `m001.spc` (+ `m000.set` beside) -> one `m000.pto` beside the first, verified -> drop `m000.pto` -> `m000.spc`, `m000.set`, `m001.spc` written back byte for byte. Data: `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna`.

## 9. Persistence, guide, help, docs

`export_settings`: `history` (documentary), `last_dir` (the Qt tool remembered window geometry only). Guide: 5 steps, 1 await (`request_add`). Help: no links. Docs: the tool is described in `docs/guides/74_intensity_traces_and_file_tools.md`; not changed (behaviour of the Qt tool unchanged).

## 10. Blocked / open

none for the plugin; `emtk_preview.json` untouched (reviewer removes `tttr_to_pto` after accepting). Open emtk gap: no translation hook in `view_form`.
