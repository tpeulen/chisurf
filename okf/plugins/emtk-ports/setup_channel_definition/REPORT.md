# emtk port report — `setup_channel_definition` (settings plugin upgrade)

Upgrade by the implementing agent (Sonnet), 2026-10-01, following UPGRADE_BRIEF. Board entry `T-20261001-SCD`.
**Recommendation: keep on the preview list.** The plugin's own app is at parity for the toolbar, setup CRUD, reading, LUT rules,
help, guide and tests; the detector *table*, a few Qt entry formats and two Qt hand-offs live in the shared editor
(`chisurf/emtk/channel_definition.py`, not edited) and are listed below. The reviewer decides.

## 0. Header

| Field | Value |
|---|---|
| Plugin | `setup_channel_definition` (`chisurf/plugins/core/setup_channel_definition`) |
| Port type | upgrade of an existing emtk app (Type A/B hybrid: the app hosts the shared editor and adds the Qt toolbar) |
| Commits | `707df5594` Qt baseline and current emtk state (pre-upgrade/); `5617dd523` emtk app at parity; evidence commit follows |

## 1. State at start

`git status --short`: ` M __init__.py`, ` M manifest.json`, `?? gui/app.py` (earlier stream; preserved in `pre-upgrade/`). Files not mine that I had
to edit: none (the shared editor and `chisurf/core/setup_channel_definition.py` are untouched).

## 2. Qt checklist (all controls) and where each is in emtk

Toolbar (now one row in the app): Setup combo, Save, Rename, Delete, Public, Calibration, Help (Guide added). Tabs: Setups, TTTR reading,
Detectors, PIE windows, TAC corrections, Optical setup (shared editor). Per control: `compare.json` explained (45 entries, each names tab and
label) and test `test_every_qt_control_is_reachable_in_one_of_the_six_tabs` (33 Qt controls checked against the drawn strings of each tab).

| Status | Qt control |
|---|---|
| done in the plugin app | Setup combo, Save (name prompt), Rename (name prompt, overwrite confirm), Delete (confirm), Public (owner only), Calibration (Latest = no-op), Help, Guide, window title, LUT gate switches on when a LUT is added |
| present in the shared editor (tab) | file type, Read, macro/micro tick, binning, effective tick, Plot toggle, PIE add/remove/rename, detector add/remove/rename, channels, ranges, G, l1, l2, G channels, Calculate G, Polarization resolved, Apply LUT, LUT per channel, shift, Assign LUT, optical setup |
| deliberate (`deliberate.json`) | Edit JSON (hidden in Qt itself); Configure LUTs... (opens the LUT Tools plugin: replaced by inline compute/assign/export/remove); Adjust shifts... (visual dialog: replaced by the shift input + preview) |
| blocked on the shared editor | table layout of detectors, full-width stacked buttons on the Setups tab, restoring the last tab, Qt-accepted range formats (see 10) |

## 3. Files

`gui/app.py` (rewritten), `gui/model.py` (new, Qt-free `SetupToolbar`), `gui/help.md`, `gui/guide.json` (8 steps, 3 awaits), `test/__init__.py`,
`test/driver.py`, `test/reference.py`, `test/test_emtk_setup_channel_definition_parity.py`, manifest (`make_app`; `create_app` kept as alias),
`test/plugin_help_guide_allowlist.txt` (struck this plugin). No `*.view.json`: the shared editor is hand-drawn, the toolbar is hand-drawn (allowed:
toolbar/status strip); this is a deviation from the brief's spec rule that I cannot fix without editing the shared editor.

## 4. Automated evidence

```
compare: exit 0 / lost [] / stale_explanations [] / explained 45 / untooltipped []   qt-free True
after: 29 controls, 0 without tooltip, qt-free=yes
```
The tool records only the first tab (Setups), hence 45 `explained` entries; every other tab is in `after_tab_<name>_<size>.png`.

## 5. Deliberate differences

See `deliberate.json` (45). Behavioural: Rename onto an existing name asks "overwrite?" as Qt does; Public stays on a renamed setup (Qt drops it);
the status line replaces Qt's "Success/Error" message boxes; setup choice labels the empty entry "Unsaved"; the last-used pointer is not written on
selection and not opened at start (core model API gap); detector defaults of "Add detector" differ (chs [0], 0:32768 vs Qt "0, 1", 0:2048).

## 6. Tests

```
$ python -m pytest chisurf/plugins/core/setup_channel_definition -q -p no:cacheprovider
53 passed, 1 xfailed, 17 warnings in 42.24s
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
13 passed in 34.98s
```
The plugin had 0 tests before. Highlights: setup save/rename/delete/public equal the Qt tool in a JSON file (in process) and in a temporary MMFDB (subprocess
`test/reference.py`, own environment, two databases); rename overwrite accept/decline; reading `BH_SPC132.spc` gives Qt's timing (13.5 ns, 3.2958984375 ps)
and identical per-channel decays; LUT assign equals Qt and turns the gate on; compute/export/shift/remove LUT; one tooltip test per tab and per prompt;
every Qt control reachable; toolbar is one row and wraps at 800 and 520 px; guide targets exist and Save advances the tour; settings round trip; Qt-free.
Deliberate breakage: `delete()` made a no-op and the LUT-gate rule disabled: 4 tests failed (`test_save_rename_delete_in_a_setups_file_equal_the_qt_tool`,
`test_crud_and_calibration_in_the_mmfdb_equal_the_qt_tool`, `test_assigning_a_lut_stores_it_and_switches_the_gate_on_like_qt`,
`test_compute_shift_export_and_remove_a_lut`); restored, 53 pass. Pre-existing failures elsewhere (not mine): `test/test_plugin_help_guide_seam.py` and
`test/test_prd_mentions.py` fail for ~23 other plugins; none for this one.

## 7. Screenshots read (all full size)

Qt: `before.png`, `before_populated_{saved,read,plot,windows,lut,optical_dialog}.png`. emtk before: `before_emtk_tab_*`. After: `after_1200x800`,
`after_800x600`, `after_empty_*`, `after_tab_{setups,tttr_reading,detectors,pie_windows,tac_corrections,optical_setup}_{1200x800,800x600}`,
`after_populated_saved_calibration_*`, `after_populated_prompt_{save,rename,delete}_*`, `..._overwrite_1200x800`, `..._no_selection`, `..._help`, `..._guide`, `..._narrow_520x500`.
Seen and fixed: the calibration combo clipped a timestamp (widened to 190 px); a dialog drawn at 1200 then 800 sat off screen (emtk keeps the dialog position; evidence taken
800 first); a stray hover tooltip in a capture (pointer moved away). Not visible: clipped labels, overlaps, empty panels, plot without axes. Qt note: the Qt micro-time preview
plot does not render offscreen (pyqtgraph), so no Qt plot picture exists; the emtk plot shows the four routing channels.

## 8. Workflow

Choose a setup, edit tabs, Save (prompt) -> stored; tick Public (owner) and Save; pick a calibration snapshot; Rename; Delete: all via `SetupToolbar`,
tested against Qt. Data: copy of `test/data/tttr/BH/132/BH_SPC132.spc`.

## 9. Persistence, guide, help, docs

`export_settings`: working definition, tab, setups file (as before). The tab cannot be restored in a wide window (the editor owns it). Guide: 8 steps, targets are the
toolbar controls and the prompt button, `await` on setup choice, Save, prompt (tested for Save). Help: `help.md` with a live link (`test_plugin_help_guide_seam` for this
id: 2 passed, 1 skipped). Docs gap: no guide page for this plugin; `okf/log.md` bullet added; `emtk-migration-inventory.md` is untracked (another stream's), not edited.

## 10. Blocked / open items (shared editor and core; not edited)

1. Detectors are collapsible blocks, not the Qt table; Setups tab stacks full-width buttons (the toolbar row compensates).
2. Range text: `20:10`, `5:5`, `0:10;20:30` accepted by Qt, rejected by the editor (test `..._differs_from_qt`). Repro: `ChannelDefinitionWidget._parse_ranges("20:10")`.
3. With a fixed File Type, reading a text file renamed `.ptu` succeeds and overwrites the timing with nonsense (xfail test). Repro: `page.read(bad)` with `file_type SPC-130`.
4. Last tab not restorable; no Configure-LUTs / visual shift hand-off; last-used setup not persisted/opened (core `refresh_setups` drops it).
5. **Core bug (any save on a fresh MMFDB is lost):** `MFDatabase(p)`; `setup_store.save_setup_row(db, CONFIG, "Mine", {"windows": {}}, user_id="new")`;
   `len(db.list_setups())` is 1; `db.close()`; `len(MFDatabase(p).list_setups())` is 0 (`ensure_user` leaves a transaction open). Tests seed the user.
6. Qt defects found (not fixed, legacy): calibration combo never lists snapshots (missing `prefix` argument swallowed); rename drops Public. In `okf/references/known-issues.md`.

## 11. Definition of Done

D1 yes; D2 yes with 3 deliberate + the shared-editor items above; D3 yes; D4 yes (both sizes, empty and populated, every tab); D5 yes; D6 partly (tab); D7 yes;
D8 gap noted; D9 yes; D10 yes.
