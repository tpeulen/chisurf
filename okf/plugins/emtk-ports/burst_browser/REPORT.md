# emtk port report — `burst_browser` (swap-candidate, audit-all row 26)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_browser` / `chisurf/plugins/burst/burst_browser` |
| Port type | B (run port): the Qt `BurstBrowserWidget` already draws `BurstBrowserApp` in a `ControlHost`, adding QFileDialogs, a synchronous load and the workflow API (`table`, `load_folder`, `load_bur`); the emtk app runs the same drawing with the stream's `BurstBrowserController` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `330ea02eb` baseline; `92f69d5ca` emtk app at parity with the Qt tool; evidence commit "burst_browser: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py` (lazy export, widget moved to `gui/tool.py`), `gui/__init__.py`
(dropped the AutoForm `sections` registration), `gui/app.py`, `manifest.json` (emtk entrypoint), `view_model.py` (cancel
check, selection reset); untracked `gui/controller.py`, `gui/tool.py`, `test/test_native.py`. All committed with the app.

**Pre-upgrade regression:** the stream's `BurstBrowserApp._render` never called `controller.poll()` or
`controller.draw_dialogs()`. In the real app Open Folder / Open File / MMFDB datasets showed nothing and a load never finished;
`test_native.py` hid it by polling by hand.

## 2. Parity checklist (`before_populated.png` vs `before_emtk_populated_*` → `after_*`)

| Qt widget | Stream's emtk | Now |
|---|---|---|
| Open Folder: QFileDialog "Select folder with .bur files" | FileDialog never drawn | sized dialog, Qt title (`test_the_folder_dialog_loads_by_drawing_frames`) |
| Open File: "Select burst file", filter `*.bur *.pto` + All | never drawn; filter `*.bur *.pto *.h5 *.hdf5` | Qt title and filter; `.bur` → `load_bur`, else `load_folder` |
| synchronous load | worker, never polled | worker, polled each frame; 10 Hz frames while reading |
| drop on the host: ignored (app had no hook) | `on_paths_dropped` | same (gained) |
| workflow API `table` / `load_folder` / `load_bur` | present | same; loads by frames alone |
| — | MMFDB datasets, Export gated / selected, Clear, Stop | kept (gained; picker now drawn) |
| status: gates pane live count | plus a copy in the Data pane that went stale | Data pane shows only controller messages |
| window min size 820×560 | host's | host's |

Shared drawing (both hosts), fixed: table headers overlapped (stretched columns narrower than their names → fixed widths that
fit); photon-size gate showed "39" for 399 (steppers at half width → no steppers); "Clear Sel" cut off at 800 px (wraps);
guide: all four steps targeted `browser_controls`, never drawn → eight steps on real controls (open_folder, detector,
hist_column, e_range, region_presets, table, browser_histogram, export_gated), action steps awaiting their use.

## 4. Automated evidence

```
after: 32 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_browser
compare: exit=0   (lost [] / stale_explanations [] / untooltipped [];  the Qt side inventories 0 controls: one canvas)
```

## 5. Deliberate differences

None in `compare.json`. Behaviour: load on a worker (Qt blocked); drop accepted; size gate without steppers; the extra
controller controls above.

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_browser -q -p no:cacheprovider
16 passed in 24.01s
```

`test/demo_folder.py`: two zero-interleaved `.bur` tables, 300 bursts, low FRET / high FRET / donor-only in 2 : 2 : 1.
`test_emtk_browser_parity.py` (12): rows, gated rows (120 = the high-FRET population), E histogram and status equal the Qt
widget's (subprocess) and the drawn status follows the gates; the folder dialog opened by a pointer press, the first guide step
released by it, a pick loading by drawn frames alone; a drop and `load_bur` likewise; frames requested while reading;
per-action dialog titles/modes and the Qt filter; gated and selected CSV exports; errors; every guide target drawn; draws empty
and populated at 1200×800 / 800×600 with fixed column widths wider than their headers; Qt-free; tooltips.

Deliberate breakage, round 1: `poll()` removed from the render → dialog and drop tests failed; fixed widths removed → draws test
failed. Round 2: table rect not remembered → guide-target test failed; Qt filter changed → dialog test failed. All restored.

## 7. Screenshots read

`before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,800x600}.png`,
`after_gated_1200x800.png` (120 / 300, S histogram), `after_file_dialog_1200x800.png`, `after_*`.

## 9. Persistence, guide, help, docs

Window geometry (manifest) on the Qt side, host's in emtk; settings not persisted by either. Guide rewritten (both hosts read
it: the Qt widget's `tour_target` resolves the same names). Help unchanged. Docs: none.

## 10. Blocked / open

* Histogram gate tags ("E min: …") sit on the x tick labels (implot `tag_x` placement), both hosts.
* `gui/sections.py` and `gui/burst_browser.view.json` (the pre-emtk AutoForm surface) are no longer used by either host;
  `view_model.view_spec()` still points at the spec. Left for a cleanup change.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
