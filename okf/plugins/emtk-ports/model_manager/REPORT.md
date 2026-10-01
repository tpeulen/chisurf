# emtk port report — `model_manager` (settings plugin upgrade)

Upgrade of the earlier stream's deficient emtk app by the implementing agent (Sonnet), 2026-10-01; the agent could not write
this file, so the reviewer saved its hand-over text and appended the review. Commits: `815579d57` Qt baseline and current emtk
state (with `pre-upgrade/`: the earlier stream's `app.py`, `strings.py`, `test_native.py` and the diffs of `__init__.py` and
`manifest.json`), `da776d069` emtk app at parity with the Qt tool, `9a6d99fde` evidence and report. Board entry `T-20261001-MM`.

## State at start

The plugin folder was not clean: the owner waived the precondition for exactly `__init__.py` (lazy Qt imports) and
`manifest.json` (the emtk entrypoint), both modified, and `gui/app.py` (a 73-line text-line app), `gui/strings.py`,
`test/test_native.py`, all untracked, which were preserved first. `__init__.py` and `manifest.json` were committed unchanged,
`gui/app.py` was rewritten completely, `test/test_native.py` updated (its two tests keep their meaning), `gui/strings.py`
committed untouched and no longer imported (dead code, may be deleted).

## What the Qt tool offered and what the emtk app does (25 controls enumerated)

* **Table:** `data_table` (columns Model / Experiment / Status / Spec / Parameter UI / Shared, sortable headers with tooltips,
  a filter box matching any cell, a column picker, a row-count line, `row_key` so the selection survives sort and filter).
* **Buttons:** Save, Revert (asks first, or says "Nothing to revert."), Rescan (on a `SnapshotJob`), Drop stale (asks and lists
  the names), Copy, Export CSV (`FileDialog`).
* **Right window:** Show disabled models, the status line, the selected-model pane (Markdown details with the shared-name
  callout) and the Disabled switch; Help and Guide wired as in the accepted ports.
* **Shared view model:** `view_model.py` fixed a real bug (a stale status such as "Unsaved changes discarded." hid "unsaved
  changes") and selects by row key; `api/records.py` adds `key` to the table record.
* **Deliberate differences:** hide-empty-columns and value shading with its (Qt-disabled) scope button not offered; Paste and
  Select all not offered (read-only, single selection); the close-with-unsaved-changes prompt is a status line ("unsaved
  changes"), since `ImApp` has no close veto; 84 `deliberate.json` entries are inventory artefacts of the Qt table's cells (row
  numbers, `?`, the hidden Module column, rows below the fold of the virtualised table). No control is missing.

## Evidence and tests

```
$ python -m pytest chisurf/plugins/core/model_manager -q -p no:cacheprovider
46 passed in 54.92s            (re-run by the reviewer)
$ python -m test.gui.emtk_port_parity compare model_manager --out okf/plugins/emtk-ports/model_manager
lost [] / stale_explanations [] / explained 84 / untooltipped []   qt-free: True   exit=0
after: 62 controls, 0 without tooltip, qt-free
```

31 new tests in `test/test_emtk_model_manager_parity.py`, hermetic (temporary settings folder; Save is verified by reading the
temporary `settings_chisurf.yaml`): rows and status equal the Qt widget's for the real registry (40 models), filter, sort, Show
disabled, detail pane (several models, shared name, missing spec), toggling Disabled / Save / Revert / Drop stale / Rescan /
export error, the confirm dialogs, empty registry shows a message and no invented rows, draws at 1200x800 and 800x600, tooltips
(inventory plus a spec walk including columns), Qt-free, settings round trip, guide targets and awaits, help links. Deliberate
breakage (restored): `save()` writing an empty list and `confirm_yes` doing nothing for revert each failed their test.
Screenshots (empty, populated, selected, shared name, dirty, filter and sort, confirm dialog, hidden disabled rows, 1200x800 /
800x600 / 500x500) were read at full size; at 800x600 two columns are shortened with an ellipsis and the table scrolls sideways.

## Open points

No close veto in `ImApp`; the painted table has no clipboard or context menu (buttons instead); emtk Markdown draws a plain `>`
quote under an empty `[]` title (repro `im.markdown("> hello")`, worked around with a `> [!WARNING]` callout); no docs guide page
exists for this plugin (only the generated catalogue).

## Review (reviewer, 2026-10-01)

Verified, not taken from the hand-over: commits touch only `model_manager` files, its evidence and the agent's log hunk; 46 tests
pass; `compare` exit 0 with `lost` `[]`; no Qt imports in `gui/app.py` / `gui/model.py`; the real MMFDB file is untouched; the
populated screenshot read next to `before_populated_selected_shared.png`: same 40 rows, columns, selection, detail pane with the
shared-name warning, Disabled switch, and the same status line ("40 models · 0 disabled · 2 disabled name(s) match no model").
**Accepted.** The plugin is removed from `emtk_preview.json` (the swap): `model_manager` now opens in emtk by default.
