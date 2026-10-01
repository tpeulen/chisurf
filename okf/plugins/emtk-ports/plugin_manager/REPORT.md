# emtk port report — `plugin_manager` (settings plugin upgrade)

Upgrade of the earlier stream's deficient emtk app (a text list of "Name [built-in]" lines, no columns, search or dependency table) by the
implementing agent (Sonnet), 2026-10-01; the agent could not write this file, so the reviewer saved its essentials and appended the review.
Commits: `f632b55e5` Qt baseline and current emtk state (with `pre-upgrade/`), `b7de3750b` emtk app at parity (with the earlier stream's
`__init__.py`, `manifest.json`, `api/settings_io.py`, `view_model.py`, `test_native.py`, `test_launcher_dispatch.py`), `581d9bd9d` selected-plugin window
460 px, `951af9d7d` evidence. Board entry `T-20261001-PM`.

## What changed

* **Plugin table:** `gui/plugins_emtk.view.json` + new Qt-free `gui/model.py`: a `data_table` with the Qt's six visible columns (Plugin / Version /
  Category / Status / Requires / Required by) and five hidden ones, filter, sort, column picker, row count, Show disabled, and the status line; cells are
  proven equal to the Qt widget cell by cell for the real 132 plugins.
* **Selected plugin:** details, Disabled, Show in main toolbar, both window-state choices, the kept GUI-runtime choice, and a dependencies `data_table` with its
  own filter and row count.
* **Actions:** Save, Revert (asks first), Rescan, Install (zip, then folder if cancelled; validation, confirmation), Uninstall (confirmation with path and hard
  dependants; built-ins refused), Move up / down, Rename, the Icon panel, Open folder, Copy, Export CSV. Confirmations, notices and the rename prompt are in-app
  dialogs; Rescan, Install, Uninstall and icon generation run on a `SnapshotJob`.
* **Shared view-model fixes** (both windows): `show_disabled` is a settings-backed property (every reload used to reset it, hiding rows again in the Qt tool);
  `save()` returns whether it wrote the file; a stale status no longer hides "unsaved changes". The icon test now expects 256 px, matching the Qt panel.
* Guide of 8 steps (awaits `row_selected`, `save`), help updated.
* **Deliberate differences** (402 `deliberate.json` entries, all `explained`): 388 table-cell texts (the Qt inventory lists every cell of a fully laid-out table;
  the emtk table draws the rows in view and shortens long cells, full text as tooltip; equality of all 132x11 cells is tested); `?` is Help; hide-empty-columns and
  shade-by-value not offered; the details pane is plain text without the requires / required-by lists (the same edges are in the Dependencies table); the icon chooser
  has no svg; no close veto (status line says "unsaved changes").

## Evidence and tests

```
$ python -m pytest chisurf/plugins/core/plugin_manager -q -p no:cacheprovider
90 passed in 39.32s        (re-run by the reviewer; 41 earlier + 49 new)
compare: exit 0 / lost [] / stale_explanations [] / explained 402 / untooltipped []   qt-free True      after: 85 controls
```

**Safety (this plugin installs and deletes):** the 49 new tests use temporary settings and a temporary user-plugins directory, wrap `shutil.rmtree` so that any removal
outside `tmp_path` fails, compare the real `~/.chisurf/plugins` and the built-in `core/about` folder before and after, and use no pip or network. Install from a throwaway
zip and folder (wrapped zip, overwrite, five refusal reasons including path traversal and no manifest), Uninstall of a user plugin (confirmed / declined) and the
refusal for a built-in were checked with before/after directory listings. Deliberate breakage (`do_install` not installing, `revert` not reverting) failed 5 tests;
restored.

## Open points

emtk gaps found (not patched): the painted Markdown drops the underscores of words with two of them, even in code spans (`traj_energy_calculator` draws
`trajenergycalculator`); `begin_child` does not clip drawn content (a long Markdown block overdraws the text after it). At about 500 px wide the right window's labels
are cut (800x600 and 1200x800 are clean). No docs guide page exists for this plugin.

## Review (reviewer, 2026-10-01)

Verified, not taken from the hand-over: 90 tests pass; `compare` exit 0 with `lost` `[]`; no Qt imports in `gui/app.py` / `gui/model.py`; my run changed no real
settings or plugin files (the real `~/.chisurf/plugins` does not exist; built-in plugin folders unchanged by this plugin); the populated screenshot shows the
same table (six columns, 132 rows), selection with details, the dependencies table (requires / optional for, bound, installed, status) and the status line
"134 plugins · 2 disabled · 1 needing attention" as the Qt tool. **Accepted.** `plugin_manager` is removed from `emtk_preview.json`: its emtk window is now the default.
