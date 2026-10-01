# emtk port report — `chimol` (swap-candidate upgrade, audit-all row 1)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `chimol` / `chisurf/plugins/chimol` (engine: chimol repository, `modules/chimol` → `~/dev/chimol`, not edited) |
| Port type and why | A (adapter): `app.py` (earlier stream, uncommitted) already embedded chimol's toolkit-free `ChimolApp` in emtk; the work was parity, Help/Guide, routing, tests |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort spent (hours) | ~1.5 |
| Commits | `22e2f4f98` chimol: Qt baseline and current emtk state; `64e273c48` chimol: emtk app at parity with the Qt tool; evidence commit "chimol: evidence and report" (this file) |
| Agent-board entry | `T-20261001-EMTK1` |

## 1. State at start (P1)

```
 M chisurf/plugins/chimol/manifest.json
?? chisurf/plugins/chimol/app.py
?? chisurf/plugins/chimol/capture_native.py
?? chisurf/plugins/chimol/test/renders/native-narrow.png
?? chisurf/plugins/chimol/test/renders/native-normal.png
?? chisurf/plugins/chimol/test/renders/qt/
?? chisurf/plugins/chimol/test/renders/visual-verdict.json
?? chisurf/plugins/chimol/test/test_emtk_host.py
```

All of these are the earlier migration stream's (copies and the manifest diff in `pre-upgrade/`); committed with the app.
Files I did not write but edited: `app.py` (the stream's adapter, waived by the brief).

## 2. What the Qt tool offered — control checklist

The Qt `MolViewPluginWindow` shows **no Qt control**: its menu bar and status bar are hidden, its toolbar is detached and its
orphan panels are hidden (`_detach_orphan_widgets`); the visible widget tree is `QWidget`, `Viewer`, `WgpuRenderer` (measured
by `scripts/capture_qt_populated.py`). Every control is chimol's in-viewport chrome, which both hosts draw from the same
tables. The parity tool's widget grab of the Qt window is blank (`before.png`: WebGPU pixels are not in the backing store), so
the Qt baseline was taken through chimol's renderer (`chisurf.plugins.chimol.test.screenshot.grab_window`).

| # | Qt control | Where | emtk equivalent | Present? |
|---|---|---|---|---|
| 1 | Menus File, Edit, Display, Setting, Demo, Tools, Help, Density (every entry and its command) | in-viewport menu bar | same chrome; `test_menus_and_toolbar_match_the_qt_window` compares the flattened tables | yes |
| 2 | Toolbar Open, Plane, Surf, Cfg, AA, SS, Seq, Info, Density, Tree | in-viewport row | same, same test | yes |
| 3 | Sequence strip | top | same chrome (numbering differs, see 10) | yes |
| 4 | Object List (all / objects / sele, A S H L C menus, eye) | top right | same chrome; object names equal (`test_loaded_structure_matches_the_qt_window`) | yes |
| 5 | Mouse block (mode table, State, Stride, Avg) | bottom right | same chrome | yes |
| 6 | Command prompt + message line | bottom of the frame | same chrome; commands run through the same `Cmd` | yes |
| 7 | Mouse orbit / pan / zoom / pick, keys | viewport | forwarded to chimol's canvas handlers (`test_native_input_forwarding`) | yes |
| 8 | Movie playback clock | viewport | `animating()` + `command.executed` wake (`test_native_playback_*`, `test_native_mplay_*`) | yes |
| 9 | Help / Guide | — (Qt host had none; allow-listed `modules/chimol/chimol/hosts/qt`) | status-strip buttons, `help.md`, `guide.json` | added |
| 10 | Status "ChiMOL · N object(s)" | — | host status line, now counts listed objects | added (earlier stream), fixed |

Screenshots: `before.png` (tool grab, blank), `before_populated_empty.png`, `before_populated.png`,
`before_populated_800x600.png` (Qt via renderer), `before_emtk_{empty,populated}_{1200x800,800x600}.png` (the earlier app).

## 3. Files

| File | New / changed | Purpose |
|---|---|---|
| `app.py` | changed (stream's file) | Help/Guide in the strip, tour targets (`structure`, `viewport`, `command_line`, `help`, `guide`, `status`), tour awaits fed by load / drag / `command.executed`, pointer routing `_inside`, listed-object count, `export_settings`/`restore_settings` |
| `help.md` | new | window, opening, mouse, command line, objects, links |
| `guide.json` | new | 5 steps, 3 awaits |
| `test/test_emtk_chimol_parity.py` | new | 12 tests (section 6) |
| `test/test_emtk_host.py`, `capture_native.py`, `test/renders/*` | stream's, committed unchanged | host tests, capture helper, renders |
| `manifest.json` | stream's change committed | `entrypoints.emtk` → `chisurf.plugins.chimol.app:make_app`; `gui` kept |

Qt files untouched: everything under `chimol.hosts.qt` (chimol repository). No spec: the surface is chimol's chrome, which a
`view.json` cannot express (PRD rule 4: canvas).

## 4. Automated evidence (paste)

`compare` (after `deliberate.json`):

```
$ python -m test.gui.emtk_port_parity compare chimol --out okf/plugins/emtk-ports/chimol; echo "exit=$?"
exit=0
compare.json: lost [] / explained {"1": ...} / stale_explanations [] / untooltipped []
```

`after`:

```
after: 3 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/chimol
```

`qt_free`: `{'ok': True, 'output': 'QT-FREE OK\n'}`. `controls_without_tooltip`: `[]`.

## 5. Deliberate differences

| Lost/changed item | Why | Where it went |
|---|---|---|
| `1` | row header of a table in one of the Qt window's hidden orphan panels; not visible to the user | n/a (inventory artefact, `deliberate.json`) |
| Status strip under the viewer | the host needs a place for Help/Guide and the object count; chimol's prompt stays inside its frame | 26 px strip |
| Render width clamped to ≥ 760 px | chimol's chrome overprints below that; the frame is scaled to narrower windows | earlier stream, kept |

Not deliberate and **not fixed** (chimol repository; known issue "chimol: the toolkit-free host loads a PDB through a different
route than the Qt window"): with `148l.pdb` the Qt window draws the hetero groups as spheres and numbers the strip from 0 with
an extra leading code and "… and 1 more chains"; the emtk host (= `python -m chimol`) draws no hetero spheres, numbers from 1,
and shows the info panel on load (the last one deliberate in chimol's `ViewerHost`). Atom count (1363) and object list agree.

## 6. Tests (paste)

New and host tests:

```
$ python -m pytest chisurf/plugins/chimol/test/test_emtk_chimol_parity.py chisurf/plugins/chimol/test/test_emtk_host.py -q -p no:cacheprovider
20 passed in 24.15s
```

Full plugin folder: one process is SIGKILLed (exit 137, memory) at 80 % on
`test_session.py::test_loading_a_missing_file_says_which` (passes alone: `1 passed in 2.49s`), twice at the same place, so
the folder was run in two parts:

```
$ python -m pytest chisurf/plugins/chimol -v --tb=line     # parts 1: 3202 results before the kill, 15 FAILED, 40 SKIPPED
$ python -m pytest <the 48 files not reached> -q --tb=line  # part 2
7 failed, 771 passed, 2 skipped in 272.32s (0:04:32)
```

Tool self-test (`test/gui/test_emtk_port_parity.py`) is inside the guard run below and passed.

| Required test | Test name | What it asserts |
|---|---|---|
| 1 reference result | `test_loaded_structure_matches_the_qt_window` | object names and atom count equal the Qt window's after `load 148l.pdb` |
| 1b chrome | `test_menus_and_toolbar_match_the_qt_window` | every menu entry, toolbar button and command equal |
| 2 actions and errors | `test_help_and_guide_open_and_a_bad_load_reports`, `test_a_click_on_help_does_not_reach_chimol` | Help/Guide open; a bad path adds nothing and raises nothing; the strip does not reach chimol, the viewport does |
| 3 spec keys (no spec) | `test_every_guide_target_is_a_drawn_region` | every guide target is a drawn, non-empty rect inside the window |
| 4 draws | `test_app_draws_empty_and_populated[1200x800, 800x600]` | count line 0 → 1 object, Help/Guide drawn, frame ≥ 760 px |
| 5 end to end | `test_the_tour_waits_for_load_drag_and_command` | the tour waits and continues on a real load, drag and command |
| 6 Qt-free | `test_port_is_qt_free` | `qt_free("chimol")` |
| 7 tooltips | `test_every_control_has_a_tooltip` | inventory `controls_without_tooltip == []` |
| 8 persistence | `test_settings_round_trip` | `{}` round trip; manifest `settings_key` null, emtk entrypoint |

Deliberate breakage:

| Test | What I broke | Result |
|---|---|---|
| `test_a_click_on_help_does_not_reach_chimol` | `_inside` returns True | `AssertionError: the status strip belongs to the host` |
| `test_app_draws_empty_and_populated`, `test_the_tour_waits_...` | count `viewer.objects` again | `3 failed` (`assert False` line 195, `assert not True` line 207) |

Restored, `diff` clean.

Pre-existing failures I did not cause (none imports the adapter): `test_chimol_editing` (2: `ViewTuple` has no `startswith`,
pseudoatom), `test_command_line::test_the_dom_key_names_translate` and `test_keyboard_layout::...browser_host...`
(emtk `WebPage` has no `_pressed_keys`), `test_file_dialogs::test_open_save_and_render_through_the_dialog`,
`test_iterate_alter_spectrum` (3, pseudoatom), `test_object_menu_actions` (7, `symexp` 'object' argument unsupported),
`test_settings` (2), `test_split_chains`, `test_transform_sync` (173.525 vs 179.03 ± 5.37), `test_unit_cell` (`symexp`),
`test_viewer_api_is_the_face` (`atomSelectionChanged`), `test_web_parity` (`help` answers differently). Guard files: 21
failures in `test_plugin_help_guide_seam.py` / `test_prd_mentions.py`, none naming chimol.

## 7. Screenshots I looked at

| File | Observation | Fix |
|---|---|---|
| `after_1200x800.png`, `after_800x600.png` | empty viewer, chrome complete, strip with count | count read "1 object(s)" with nothing loaded → fixed |
| `after_populated_1200x800.png` / `_800x600.png` | 148l cartoon, strip, object list, mouse block, info panel, Help/Guide right | none |
| `after_populated_help_*.png` | help window fits at 800x600; `**bold**`/backticks drawn literally | shared help renderer (`chisurf/emtk/help_guide.py`), same in accepted ports; not mine to edit |
| `after_populated_guide_*.png` | step 4 card, prompt highlighted | none |

No clipped label, no text past its box, no overlapping windows, no empty panel, no oversized status box.

## 8. Workflow walk-through

`chimol/data/demos/148l.pdb`: Open (File → Open / `load <path>`) → `cmd.do("load …")`, object list gains `148l`, guide step 2
continues; left drag → `on_pointer_press/move/release`, step 3 continues; Return + `show sticks` → `command.executed`, step 4
continues; Help → help window.

## 9. Persistence, guide, help, docs

* `export_settings()` = `{}`; Qt remembered nothing of its own (`settings_key` null); chimol persists its window layout on both hosts.
* Guide: 5 steps; targets `structure`, `viewport`, `command_line`, `help` (+ an intro without target); awaits on load, drag, command, verified by test 5.
* Help links: `test_help_links_resolve` passed (3 links).
* Docs: `docs/guides/44_molecular_viewer.md` ("The window": the strip with Help/Guide). `okf/plugins/emtk-migration-inventory.md` is another stream's untracked file: not edited.

## 10. Blocked / open questions

* Load-route difference (section 5, known issue): needs a structure-factory hook in chimol's `ViewerHost`; chimol repository.
* The full suite does not finish in one process (SIGKILL at ~3200 tests).
* Swap decision is the reviewer's: the UI is at parity, the hetero/numbering difference is visible in the populated state.

## 11. Self-check

- [x] D1 Qt-free `make_app()`
- [x] D2 every visible Qt control present (one inventory artefact explained)
- [x] D3 no untooltipped control
- [x] D4 screenshots read
- [x] D5 workflow tested
- [x] D6 persistence (nothing to persist, as Qt)
- [x] D7 guide + help
- [x] D8 docs
- [ ] D9 plugin folder green: no — 22 pre-existing engine failures, listed
- [x] D10 report, evidence, board

## 12. Reviewer quick check

```bash
cd ~/dev/chisurf && export QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD:$HOME/dev/emtk"
PY=~/mambaforge/envs/arm64/bin/python
$PY -m test.gui.emtk_port_parity after   chimol --out /tmp/review_chimol
$PY -m test.gui.emtk_port_parity compare chimol --out okf/plugins/emtk-ports/chimol; echo "exit=$?"
$PY -m pytest chisurf/plugins/chimol/test/test_emtk_chimol_parity.py chisurf/plugins/chimol/test/test_emtk_host.py -q -p no:cacheprovider
grep -n "qtpy\|PyQt\|PySide\|chisurf\.gui" chisurf/plugins/chimol/app.py
```
