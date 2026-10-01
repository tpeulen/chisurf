# emtk port report — `user_editor` (settings plugin upgrade)

Upgrade of the earlier stream's deficient emtk app (a text list and one flat form, over the Qt view model, no spec) by the
implementing agent (Sonnet), 2026-10-01, following the accepted `model_manager` upgrade; the agent could not write this file, so the
reviewer saved its essentials and appended the review. Commits: `28d3006fc` Qt baseline and current emtk state (with `pre-upgrade/`: the
earlier stream's `app.py`, `strings.py`, `test_native.py` and the `manifest.json` diff), `46c6bfb19` emtk app at parity, `6e4d05295`
a staged password alone enables Save and Revert, `b23cb85ec` a "Permission denied" answer is a permission, not an unreachable server,
`bbd403c48` evidence. Board entry `T-20261001-UE`.

## What changed

* `gui/model.py` (new, Qt-free `UserEditorModel`) + `gui/users_emtk.view.json` (panels `accounts`, `account`, `password`, `confirm`)
  + a rewritten `gui/app.py`; the Qt tool (`gui/tool.py`, `users.view.json`, `api/*`) is untouched.
* **Table:** `data_table` with the Qt columns (User / Username / Role / Admin / Autologin / Active), filter, header sort, column picker,
  row count, selection that survives sort and filter, Export CSV and Copy.
* **Form and dialogs:** the account form as a spec (nine text fields, a Role choice, Administrator and passwordless toggles, the shared
  validation rules with a "Cannot save yet" list); in-app dialogs for revert, delete, forced delete and the password prompt (masked
  entries, strength bar, requirements, mismatch and weak-admin refusals). Reload, save and delete run on a `SnapshotJob`.
* Toolbar Save / Revert / Reload / New / Delete / Password... and Help / Guide; guide of 6 steps (4 awaits), help updated.
* **Shared view-model fixes** (both windows): a stale status no longer outlives its selection; a server "Permission denied" gives the
  administrator message instead of "Could not reach the MMFDB server".
* Test support: `test/seeded_db.py` seeds a temporary MMFDB through the real in-process RPC services; nothing touches `~/.chisurf`.
* **Deliberate differences:** hide-empty-columns, colour-by-value and its scope button, and the per-column predicate filter are not
  offered; the close prompt is a status line ("unsaved changes", `ImApp` has no close veto); a free-typed Role is not possible (emtk
  `choice` is not editable: a role stored by another tool is listed and kept, never replaced by "Generic"); modal warnings are status
  messages; an empty password is refused (Qt staged it); 23 `deliberate.json` entries are inventory artefacts (row numbers, role-combo
  list entries, `?`, the row-count wording).

## Evidence and tests

```
$ python -m pytest chisurf/plugins/core/user_editor -q -p no:cacheprovider
81 passed in 15.56s        (re-run by the reviewer; 28 existing + 2 native + 53 new)
compare: exit 0 / lost [] / stale_explanations [] / explained 23 / untooltipped []   qt-free True      after: 35 controls
```

53 new tests (hermetic): rows, fields and status equal to the Qt widget's for the same seeded users; the password strength rule equal
for 8 passwords; filter, sort, selection, dirty; save, new (empty and duplicate refused), delete (only the selected account;
built-in and active refused), password set then sign-in with it, rename, flags; permission-denied equals Qt's message; an offline
server invents no rows; masked entries (no clear password in the drawn strings); both sizes; guide and help. Deliberate breakage
(`ask_delete` remembering `users[0]`; a disabled password-mismatch check) failed their tests; restored.

## Open points

Narrow 500x500: the Account pane is clipped on the right (below the 800x600 target). `gui/strings.py` is dead code. emtk gaps found
(not patched): (1) spec `value` with `kind: password` is not masked by `emtk.view_form`, so the two entries are hand-drawn with the
`PASSWORD` flag; (2) `choice` is not editable; (3) the `DialogWindow` close "x" has no tooltip; (4) `DialogWindow` keeps its position
when the frame shrinks; (5) info text does not render Markdown bold. No docs guide page exists for this plugin.

## Review (reviewer, 2026-10-01)

Verified, not taken from the hand-over: 81 tests pass; `compare` exit 0 with `lost` `[]`; no Qt imports in `gui/app.py` /
`gui/model.py`; the real MMFDB file is untouched; the populated screenshot shows the same 11 accounts and columns as the Qt tool with
the active-account star, the full Account form, and the masked password dialog (strength bar, "Passwords do not match."). **Accepted.**
`user_editor` is removed from `emtk_preview.json`: its emtk window is now the default.
