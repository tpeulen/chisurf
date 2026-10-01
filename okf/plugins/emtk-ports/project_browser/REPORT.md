# emtk port report — `project_browser` (upgrade, audit-all row 34)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `project_browser` / `chisurf/plugins/core/project_browser` |
| Port type | A+B: the Qt `ProjectBrowserTool` (toolbar, search, tree of projects/versions, save/collision dialogs) over the in-process project service; the stream's emtk app (`gui/app.py`, `gui/model.py`, `gui/controller.py` job runner) over the same service |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `3658d22f5` baseline; `2d095575f` service fix (import numbering); `2d909ceba` emtk app at parity with the Qt tool; evidence commit "project_browser: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `README.md`, `manifest.json` (emtk entrypoint); untracked `gui/app.py`,
`gui/controller.py`, `gui/help.md`, `gui/model.py`, `test/test_native.py`, `test/renders/`. All committed with the app except
`test/renders/` (the stream's own captures, left untracked). The Qt `tool.py` is unchanged (= HEAD).

## 2. A defect in the shared service (`2d095575f`)

Importing an exported version into a database that already held its project gave the project a second "v1": the archive keeps
its project id (a version moved between databases joins its project) and also kept its version number. Now numbered after the
project's newest version, branch-scoped as saving does; into a database without the project the number is kept. Guard
`test/test_import_version_numbering.py`.

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt tool | Stream's emtk | Now |
|---|---|---|
| Open/Restore: load payload, `restore_gui_from_fits` (fit windows), close | load with GUI creation skipped; **no fit windows** | load, then reopen the fits' windows (no-op without a main window); window stays open |
| Save (dialog: name, visibility, notes; "Save New Version" for a known project) | modal, same fields and title rule | same |
| Export .cs.pto / Import (collision dialog or confirm) / Delete (confirm) / Refresh | same, as modals; jobs off the UI thread | same |
| search, Show public, sortable tree, double-click restores | sortable table with expanders, double-click, context menu, Inspect view (gained) | same; columns fit their text and scroll sideways (stretched columns overlapped at 800 px) |
| no guided tour (allow-listed) | none | `guide.json` on the real controls, action steps wait (Refresh, a row, Inspect); Guide button |

## 4. Automated evidence

```
after: 25 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/project_browser
compare: exit=0   (lost: database cells only, explained in deliberate.json / stale [] / untooltipped [])
```

## 5. Deliberate differences

`deliberate.json`: the "lost" entries are cells of the seeded database (the Qt baseline reads its tree rows; the emtk inventory
is taken before the asynchronous load ends). Behaviour: the window stays open after a restore; database work runs off the UI
thread.

## 6. Tests

```
$ python -m pytest chisurf/plugins/core/project_browser -q -p no:cacheprovider
30 passed in 54.34s
```

`test_emtk_project_browser_parity.py` (11), on a scratch database per test: rows equal the Qt tree's (subprocess) cell by cell;
restore loads, reopens windows, sets the session's project; the default window restorer with and without a main window; save a
new version → export → import (joins as v4) → delete; errors in the window; guide targets drawn, the tour card drawn, awaits
released by pointer presses; draws at both sizes with fitting columns; settings round trip; Qt-free; tooltips.

Deliberate breakage, round 1: window restore removed → restore test failed; the versions rect not remembered → guide test
failed. Round 2: action presses not reported to the tour → guide test failed; `tour.draw` removed → **passed at first** (state
worked, card never shown) → the test now asserts the step title is drawn → failed. All restored.

## 7. Screenshots read

`before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,800x600}.png`.

## 9. Persistence, guide, help, docs

Search, Show public, last directory and expanded projects via `export_settings`. Help (stream's `help.md`) and the new guide;
off the help/guide allow-list. Docs: none changed.

## 10. Blocked / open

none for this plugin. Found while running the help/guide guardrail (not this plugin's, reported on the board): stale allow-list
entries and slideshow guides in other streams' uncommitted plugins, and `code_editor/gui` without help/guide.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
