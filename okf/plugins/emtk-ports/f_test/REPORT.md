# emtk port report — `f_test` (swap-candidate, audit-all row 17)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `f_test` / `chisurf/plugins/core/f_test` |
| Port type | A (view port): the Qt `FTestTool` = AutoForm over the model + a toolbar (From fit menu, Guide, ?); the earlier stream drew the same `ftest.view.json` with emtk (`gui/app.py`) and moved the model to `gui/model.py`, which the Qt tool now imports too |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `6a68d7f86` baseline; `0caebd623` emtk app at parity with the Qt tool; evidence commit "f_test: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py`, `__main__.py`, `gui/__init__.py`, `gui/tool.py`, `manifest.json`;
untracked `gui/app.py`, `gui/model.py`, `test/test_native.py`, `test/renders/`. All committed with the app except
`test/renders/native-emtk.png`, the stream's screenshot of the combo UI this change replaced (stale, left untracked).

## 2. Parity checklist (`before_populated.png` vs `before_emtk_populated_*` → `after_populated_*`)

| Qt | Stream's emtk | Now |
|---|---|---|
| Toolbar "📊 From fit" menu: a submenu per open fit, three targets each (model 1, model 2, χ²-max); rebuilt when it opens | "Open fit" combo + "Load into" combo + "Load selected fit" + "Refresh open fits" | **From fit** menu: one row per fit and target, the Qt labels, re-read on every open (`after_populated_from_fit_menu_800x600.png`) |
| Guide, ? (toolbar, right) | Help, Guide (own row) | Guide, ? beside From fit |
| AutoForm: two panels, 10 fields, coupled recompute | same spec, two docks | same |
| "(no open fits)" disabled entry | combo "No open fits" + status line | disabled "(no open fits)" row |
| Drop: status-bar "takes no dropped files" | status line | same |
| Guide step 2 text names the From fit menu | text replaced from Python to describe the combos | `guide.json` as written (emoji dropped from the await hint so both hosts render it); Python patch removed |
| window geometry (manifest statefulness) | host's | host's |

Values after the same three loads: χ²(1) 1.3100, n₁ 1021, χ²(2) 1.0200, n₂ 1019, confidence 0.99997, χ²min 1.02000, params 5,
ν 1019, χ²max 1.03113 — identical in `before_populated.png` and `after_populated_*`.

## 4. Automated evidence

```
after: 25 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/f_test
compare: exit=0   (lost [] / stale_explanations [] / untooltipped [])
```

## 5. Deliberate differences

None in `compare.json` (no `deliberate.json` needed). Layout: the two panels are two docks (comparison above, upper limit
below) rather than one scrolled form; load errors and an unreadable fit registry show in a status line under the toolbar.

## 6. Tests

```
$ python -m pytest chisurf/plugins/core/f_test -q -p no:cacheprovider
41 passed in 91.34s
```

`test_emtk_f_test_parity.py` (18): every step of three loads + four edits against the committed Qt rules written out with
scipy (`test_loads_and_edits_follow_the_committed_qt_rules`); the same trail against the Qt tool in a subprocess (wiring); the
menu entries equal the Qt menu's; each of the six drawn menu rows pressed with the pixel painter loads that fit into that
target and closes the menu; the menu re-reads the fits on reopen; "(no open fits)"; errors (fit without model, bad index,
registry raising) in the window; spec keys have model attributes and descriptions; draws empty and populated at 1200×800 and
800×600; the guide's From fit step waits for a load; Qt-free; tooltips (the From fit tooltip is the Qt button's).

Deliberate breakage, round 1: Qt label of model 1 swapped → menu test failed; refresh-on-open removed → reread test failed.
Round 2: `?` removed → draws test failed; model 2 load recomputing χ²(2) instead of the confidence → **passed at first**, because
both hosts now share the model and a later edit overwrote the difference; fixed by comparing every step against an independent
scipy reference, which then failed at step 1. All restored.

Measurement trap recorded: probing menu rows with `RecordingPainter` frames put the hits ~one row off the screenshot; its line
height is not the pixel painter's. Pointer tests must draw with `PixelPainter` (at a small size: 1200×800 costs ~1.5 s a frame).

## 7. Screenshots read

`before_populated.png`, `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,800x600}.png`,
`after_populated_from_fit_menu_800x600.png`, `after_*`. Nothing clipped.

## 9. Persistence, guide, help, docs

Qt kept window geometry only (host's in emtk); model values are not persisted on either side. Guide/help: `guide.json` and
`help.md` shared by both hosts. Docs: behaviour unchanged, none edited.

## 10. Blocked / open

none.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
