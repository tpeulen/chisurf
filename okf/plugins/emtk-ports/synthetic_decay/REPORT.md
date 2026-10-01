# emtk port report — `synthetic_decay` (swap-candidate verification and upgrade)

Agent: claude (Sonnet), 2026-10-01, per `UPGRADE_BRIEF.md`. Board entry `T-20261001-SWAP4`. Verdict: **accept** after the upgrade; the
pre-upgrade app had a **REGRESSION** against the Qt tool (below), fixed in the plugin's own app.

Commits: `bce056b82` Qt baseline and current emtk state (with `pre-upgrade/`, including the HEAD version of `view_model.py`), `a69de0c2b` emtk app at parity
with the Qt tool, `a449ab571` photon budget drawn as a whole number, `6a32e9eb1` linear axes for an empty plot and a shorter last guide step, then the evidence commit.

## 0. Pre-upgrade REGRESSION: cells of the lifetime and rotation tables could not be edited

Typing a lifetime into the table did nothing: the value snapped back and Generate used the old one, so the tool could only generate from the two default rows
unless the model was driven from code. Reproduction (repository root, state of `bce056b82`; the `_bind_tables` line below switches the fix off):

```
export QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD:$HOME/dev/emtk"
python - <<'PY'
import os, tempfile; os.environ["CHISURF_SETTINGS_DIR"] = tempfile.mkdtemp()
from emtk.testing import RecordingPainter
from chisurf.plugins.fluorescence_decay.synthetic_decay.gui import app as mod
mod.SyntheticDecayApp._bind_tables = staticmethod(lambda sections: None)   # pre-upgrade behaviour
a = mod.make_app(); [a.draw(RecordingPainter(), 0, 0, 1200, 900) for _ in range(3)]
b = a.form.tables["spectrum_source"]; b.control.begin_edit(0, "tau"); b.control.editor.set_text("2.5"); b.control.commit_edit()
print(a.model.spectrum_rows[0], repr(b.edited_call))      # {'amp': 1.0, 'tau': 1.2} ''  : the edit never reached the model
PY
```

Cause: the shared view spec says `update_call` (the Qt table's hook, `(row, key, value)`); emtk's table only reads `edited_call`, and the source returned fresh copies of the rows, so
the edited copy was thrown away on the next frame. Fixed in the plugin's own app and model (below); the Qt spec and tool are unchanged apart from two table descriptions.
Also: the Qt button emoji drew as icons in the native window (rule 6), `export_settings` / `restore_settings` did not exist, and the help window showed the Qt help's Markdown marks raw.

## 1. State at start

`git status --short chisurf/plugins/fluorescence_decay/synthetic_decay`: ` M gui/view_model.py` (now a thin Qt adapter over the shared model), ` M manifest.json`, `?? gui/app.py`,
`?? gui/model.py`, `?? test/renders/`, `?? test/test_native.py` (earlier migration stream, 2026-09-29; nothing modified in the last 60 minutes by anyone else, no foreign staged file).
`pre-upgrade/` holds `app.py`, `model.py`, the tracked diff and the HEAD `view_model.py` (the Qt tool as it was before the migration stream). The Qt tool runs on the migrated view model; the numbers
are therefore also checked against the canonical generator (`core/algorithms.py`, unchanged and tracked) and analytic expressions, not only against the Qt tool.

## 2. Checklist of every control of the Qt tool

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Generate / Save / Fit group (toolbar) | buttons, `generate` / `save` / `send_to_fit` | yes |
| 2 | Guide / ? | `Guide`, `Help` | yes |
| 3 | Lifetime spectrum table (editable Amp, tau) | spec `table` bound to the model's rows, `edited_call` | yes (was broken) |
| 4 | Add / Remove / Load (spectrum) | spec buttons (Load opens the file dialog) | yes |
| 5 | Bins, dt, Start | spec `value` fields with the same limits | yes |
| 6 | IRF path + "..." browse | text field + `Browse IRF` dialog | yes |
| 7 | Noise, Photons, Seed | spec toggle / values | yes |
| 8 | Mode: VM / VV-VH radio | spec `choice` (radio) | yes |
| 9 | VV/VH detection corrections g, l1, l2 (folded in VM mode) | folded panel, opens in VV/VH mode | yes |
| 10 | Rotation spectrum table, Add / Remove | spec table + buttons | yes (was broken) |
| 11 | Status line | `info` | yes |
| 12 | Decay plot (log y; VV and VH in VV/VH mode) and r(t) plot | `implot` windows | yes |
| 13 | Panel fold arrows | collapsible panels | yes |
| 14 | Qt file dialogs (spectrum, save, IRF) | `FileDialog` in an in-app window | yes |

Screenshots: `before.png`, `before_populated*.png` (empty, VM, VV/VH with noise, IRF, bad IRF, final), `before_emtk_{empty,populated,vvvh_noise,bad_irf}_1200x900.png`.

## 3. Files

| File | New / changed | Purpose |
|---|---|---|
| `gui/app.py` | changed | plain button labels, table binding (`_bind_tables`), whole-number photon budget, native guide/help, `export_settings` / `restore_settings` |
| `gui/model.py` | changed | `spectrum_records`, `rotation_records`, `edit_cell`, `export_settings`, `restore_settings` (the Qt adapter inherits them harmlessly) |
| `gui/synthetic_decay.view.json` | changed | a description on both tables (shared with the Qt tool) |
| `gui/guide_emtk.json`, `gui/help_emtk.md` | new | the Qt guide with an emoji-free hint; the Qt help without Markdown marks (the Qt tool keeps `guide.json`, `help.md`) |
| `test/test_emtk_synthetic_decay_parity.py` | new | 34 tests |

## 4. Automated evidence

```
compare: lost []  untooltipped []  qt-free: True  exit=0   (explained 7, stale_explanations [])
after: 54 controls, 0 without tooltip, qt-free=yes
$ python -m pytest chisurf/plugins/fluorescence_decay/synthetic_decay -q -p no:cacheprovider
65 passed in 17.97s        (31 existing + 34 new)
```

## 5. Deliberate differences (`deliberate.json`)

Numeric cells (`1.0` vs `1`), the Qt row-number header, the `?` button (labelled Help), and `g`, `l1`, `l2` listed as lost only because the panel is folded in VM mode in both windows (they are drawn in
VV/VH mode or when the panel is opened). The native plots draw their own titles; the status line sits above the form (Qt: below the tables).

## 6. Tests

| Required test | Test | Asserts |
|---|---|---|
| 1 reference result | `test_vm_decay_equals_the_canonical_generator_and_the_analytic_shape`, `test_vv_vh_pair_...g_ratio`, `test_noise_is_reproducible_by_seed_and_spends_the_photon_budget`, `test_an_irf_file_smears_the_prompt_...`, `test_the_native_app_and_the_qt_tool_generate_the_same_numbers` | decay/pair/r(t) equal `compute_decay` / `compute_aniso_decay` / `compute_rt`; a single exponential is log-linear; VH = VV/g without anisotropy; Poisson sum within 5 sigma of the budget, integer counts, same seed same data; the Qt tool and the Qt table cells equal the native model |
| 2 actions and errors | Generate, cell edits (both tables, typo), Add/Remove (both tables, last row kept), Load and Save dialogs (cancel writes nothing), save formats and the VV/VH round trip, Save/Fit before Generate and Load errors equal the Qt status texts, Fit group sink and its failure, Browse IRF, bad IRF | each button and error path |
| 3 spec keys | `test_every_spec_key_exists_on_the_model` | attr/call/source/edited_call/actions, tables bound natively |
| 4 draws | empty state message, `test_draws_empty_and_populated[4 sizes]`, no emoji, photon budget text, an empty plot keeps linear axes | 1200x900, 1200x800, 800x600, 500x500; no curve before Generate |
| 6 Qt-free | `test_port_is_qt_free` | |
| 7 tooltips | `test_every_control_has_a_tooltip` | empty and populated inventory, spec walk incl. table descriptions and columns |
| 8 persistence | `test_settings_round_trip_and_invalid_values_are_ignored` | export/restore, bad values ignored or clamped |
| also | guide targets drawn, tour waits for Generate, Qt tool keeps guide/help, help links live | |

Deliberate breakage (restored): table binding switched off and the start bin shifted by one: 7 tests failed (`test_a_cell_edit_reaches_the_model_and_the_generated_decay`,
`test_vm_decay_equals_the_canonical_generator_and_the_analytic_shape`, `test_noise_is_reproducible_by_seed_...`, `test_an_irf_file_smears_the_prompt_...`, `test_the_table_shows_rows_added_and_loaded_without_a_rebuild`, ...);
restored, 63 passed (65 with the two later tests).

Pre-existing failures: none.

## 7. Screenshots I looked at (full size)

`after_populated_vvvh_noise_1200x900.png` (three lifetimes after a cell edit, VV and VH noisy curves, r(t), g/l1/l2 shown, plain Add/Remove/Load), `_800x600` (VM decay and r(t), corrections folded),
`after_empty_*`, `after_populated_irf` (shifted prompt), `after_populated_bad_irf` (error text, empty plots), `after_populated_file_dialog`, `after_populated_help`, `after_populated_guide`, `after_populated_narrow_500x500`.
The first shot showed the photon budget as `1e+06` and an empty log plot with a 1e-21 range, and the last guide step overflowed its card; fixed (whole-number format, linear axes while empty, shorter text) and re-shot. Nothing clipped, overlapping or an empty panel; the tour's hint glyph is a blob (shared emtk font).

## 8. Workflow

Edit the lifetime cells -> Generate (VM, or VV/VH with g, l1, l2 and noise) -> Save (CSV / text / .npy / JSON, or a VV/VH file with the calibration in the footer) -> Fit group (dataset and fit group
through the sink). Data: generated by the plugin itself; the IRF and spectrum files are written by the tests.

## 9. Persistence, guide, help, docs

`export_settings`: bins, dt, start, IRF path, noise, photons, seed, mode, g, l1, l2, both tables (the Qt tool remembered window geometry only; the curves are not kept). Guide: 7 steps, 1 await (Generate).
Help: 5 doc links tested live. Docs: `docs/guides/76_decay_analysis_tools.md` is unchanged (Qt tool unchanged).

## 10. Blocked / open

none for the plugin; `emtk_preview.json` untouched (reviewer removes `synthetic_decay` after accepting). The native fit group goes through `chisurf/emtk/datasets.register_synthetic_fit` (the shared,
untracked helper of another stream; covered by the existing `test_native_fit_registration_preserves_science`). emtk note: `view_form`'s table reads `edited_call` only; a spec that says `update_call` (Qt) edits nothing.
