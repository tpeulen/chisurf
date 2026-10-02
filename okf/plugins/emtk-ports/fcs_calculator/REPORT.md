# emtk port report — `fcs_calculator` (upgrade, audit-all row 50)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `fcs_calculator` / `chisurf/plugins/fcs/fcs_calculator` |
| Port type | A: the Qt `ConfocalCalcWidget` (`wizard.py`: AutoForm over `fcs_calculator.view.json` with four custom Qt sections, Guide and ?) → a Qt-free `gui/model.py` and `gui/fcs_calculator_emtk.view.json` drawn by emtk's `view_form` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `739262295` baseline; `128672bd6` emtk app at parity; evidence commit "fcs_calculator: evidence and report" |
| Board | `T-20261002-EMTK1D` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `manifest.json` (emtk entrypoint), untracked `gui/app.py`. The stream's
numbers equalled the Qt widget's (`before_emtk_populated_*` vs `before_populated.png`), but its app had several gaps:
- sliders that dropped the decimals and clipped labels;
- no help and no guide;
- the constraint as a combo, not radios, and the dye list starting blank;
- shape defaults of 1 nm / 2 where Qt has 5 nm / 1;
- Import JSON off the bottom of the window at 800×600.

## 2. Parity checklist

| Qt widget | Now |
|---|---|
| Constraint radios Fix D / Fix rₕ / Fix Veff | radio choice; the two computed fields are disabled (Qt: read-only, greyed, no arrows) |
| τ, D, rₕ, S, Veff, T, η (two columns, spec decimals and ranges), Use water η(T) disabling η | same fields from the same spec entries, spin arrows, two columns |
| 1/N, N, Conc linked through Veff by the field typed last | same (`conc_edited` / `N_edited` / `invN_edited`) |
| dye combo (MMFDB list, first selected) + Apply Dref, scaling radios (with T/η, at 25 °C) | same; Apply Dref disabled for a species without D |
| Molecular shape (collapsed): Type, Size (nm) 0.1–1e9 = 5, Aspect 0.1–1e3 = 1 (disabled for a sphere), Apply shape→D | same, collapsed fold |
| Settings JSON (collapsed): Export / Import (sorted, indent 2; failures silent) | same; failures shown in red; a dropped .json imports |
| Guide, ? (top right) | 📖 Guide, ❓ Help (top right) |
| window geometry persisted | the host's |

## 3. Automated evidence

```
after: 36 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/fcs_calculator
compare: exit=0
```

## 4. Deliberate differences

`deliberate.json`: "?" is ❓ Help. The six controls of the shape and JSON panels sit behind their folds, which are closed by
default as in Qt, and the inventory frame draws them closed; `after_open_*.png` shows them. A failed export or import
says so: Qt failed silently.

## 5. Tests

```
$ python -m pytest chisurf/plugins/fcs/fcs_calculator -q -p no:cacheprovider
18 passed
```

`test_emtk_fcs_calculator_parity.py` (11):
- **Edit sequence:** the Qt widget replays 18 steps in a subprocess; the native app replays them through the spec's
  commit path and pointer presses. The steps are τ, c, N, 1/N, Fix rₕ + rₕ, Fix Veff + Veff, S, water off, η, T,
  dye with and without scaling, ellipsoid, cylinder, sphere, and water on. After every step the settings match
  within the Qt spin decimals, and so does which fields are editable.
- **Settings:** the Qt keys; export → import round trip; an import after the same history equals Qt's
  `_apply_settings`, including alias resolution and an unknown shape being ignored.
- **Dialogs:** export and import through the buttons; a bad file is reported; only a `.json` drop is taken.
- A species without D is refused.
- A computed field ignores typing.
- **Guide:** every target is drawn, and the τ step waits for an edit of τ.
- Guide and Help open from their buttons.
- Every panel open at both sizes stays inside the window.
- Qt-free, and tooltips in the inventory and in the spec.

The import test found a real defect: Export and Import were drawn as `…##confocal_json`, which is one ImGui id, so
Import never fired. Each button now has its own id.

## 6. Breakage check (14 faults, run twice: 13/14 caught both times)

Caught:
- computed fields editable;
- η editable with water on;
- aspect editable for a sphere;
- an N edit treated as conc;
- dye scaling ignored;
- apply keeps the constraint;
- ellipsoid axes swapped;
- dye alias not resolved;
- an unknown shape accepted;
- the error line not drawn;
- the JSON buttons sharing an id;
- the tour's shape key lost;
- any drop imported.

Missed: "shape uses the typed η". This is an equivalent mutant. While water η is on, every recompute mirrors the
water viscosity into `eta_mPa_s`, so the typed and water values agree whenever a shape is applied. The Qt widget
does the same.

## 7. Screenshots read

- `before.png`, `before_populated.png` (Qt), and `before_emtk_populated_*` (stream);
- `after_*` (default: Fix D, rₕ/Veff/η disabled);
- `after_populated_*` (ATTO 655 applied at 25 °C, Qt numbers);
- `after_open_*` (Fix Veff, water off so η is editable, cylinder, JSON panel, the red refusal for a species without D);
- `after_guide_*` (step 2 on the constraint fold).

Fixed on the way:
- the toolbar's cursor shift pushed the whole form right;
- the dye combo and Apply Dref each took a full row (Qt: one line).

No docs change: the native app does what the Qt tool does, and guide 75 only names the calculator.
