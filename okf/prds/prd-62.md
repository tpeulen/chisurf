---
type: PRD
prd: "62"
title: "PRD-62: FCS Model Consolidation — Table Views, Composable Diffusion + Bunching, Parameter-Registry Scoping"
description: Migrate the FCS MDF Gauss-Lorentz model to the table parameter view, add bunching terms to it, add a general composable FCS model (diffusion choice + bunching/antibunching terms), and fix a parameter-name registry collision (R0) with a general scoping mechanism.
status: done
phase: "unassigned"
resource: chisurf/core/models/fcs/mdf.py
tags: [prd, fcs, models, autoform, parameters, registry]
timestamp: '2026-07-23T00:00:00Z'
---

# Summary

Four related FCS asks landed together: (1) new/updated FCS models prefer the
**table parameter view** (`parameter_group_table`), and the FCS MDF
Gauss-Lorentz model was migrated to it; (2) the MDF model gained optional
**bunching** relaxation terms; (3) a **general composable FCS model** lets a
user pick a diffusion type (MDF vs. classic 3-D Gaussian, both supporting
two-focus) and add an arbitrary set of bunching/antibunching terms; (4) the
**parameter-name registry** lookup was made scope-aware so two unrelated
classes reusing the same short name (FRET's Förster-radius `R0` vs. the MDF
model's own `R0`) no longer cross-contaminate descriptions.

# Motivation

`chisurf/gui/widgets/models/fcs/mdf_widget.py` was a pre-PRD-38, hand-built
`ModelWidget`+`ModelCurve` multiple-inheritance class with 14 flat
`FittingParameter` attributes, no `view.json`, and no table view — the last
FCS model not yet migrated to the view-spec/AutoForm system (PRD-38 task 8
already flagged FCS as pending). Its `R0` parameter (the MDF's
emission-side Gauss-Lorentz waist) collided in the parameter-name registry
with FRET's `R0` (the Förster radius): `chisurf/core/parameter.py`'s
description lookup was an exact bare-name match against a single flat
`parameter_registry.json` with no per-class scoping, so the MDF model
silently inherited "Förster radius R0 of the donor-acceptor pair" as its
description — a domain-specific, wrong label bleeding across an unrelated
model. This was not a one-off: the registry generator
(`build_tools/dev_utils/export_fitting_parameters.py`) keys every
`FittingParameter(...)` call site by bare name and merges any two sites that
share one, regardless of owning class, so the same collision class was open
for the next reused name. Separately, bunching/antibunching terms only
existed inside the ~40-entry string-equation Parse-FCS catalogue
(`models.yaml`), with no way to add them to the Python-computed MDF model or
to compose them with a chosen diffusion type outside that catalogue.

# Design

## Parameter-registry scoping

- The generator now additionally emits a `by_qualified_id` index
  (`"<ClassName>.<param_name>"`, using the same "class" context it already
  scrapes via AST) alongside the unchanged bare-name `parameters` index (kept
  for backward compatibility — e.g.
  `chisurf.core.project.mmfdb_adapter.resolve_parameter_name`'s flrCIF
  `flrcif_item_id` lookup). Each bare-name entry gains an `"ambiguous"` flag
  (`true` when more than one class contributed to it).
- `Parameter.__init__`'s description lookup
  (`chisurf/core/parameter.py`) now tries, in order: (1) an explicit
  `registry_id=` against `by_qualified_id` (the namespaced convention already
  used by RICS's `registry_id="rics.D"`-style groups), (2) a class-scoped
  match derived by inspecting the constructing frame for the owning `self`
  (`_owning_class_name`, walking frames past `Parameter`/`FittingParameter`
  `__init__`s), and only then (3) the legacy bare-name entry — but only when
  it is **not** flagged ambiguous. This is strictly additive: no existing
  description is blanked, it just stops being trusted when more than one
  class shares its bare name and no more precise match exists.
- Regenerated `chisurf/core/settings/constants/parameter_registry.json`
  (`version: 2`); fixed an unrelated ASCII-mangled "Förster" → "Förster" in
  the pre-existing FRET `R0` description while there.

## MDF Gauss-Lorentz: relocate, rename, table view, bunching

- Relocated the model out of the GUI layer into
  `chisurf/core/models/fcs/mdf.py` (Qt-free `MdfFCSModel(ModelCurve)`),
  deleting `MdfFCSWidget` and its hand-built per-parameter widget list —
  matching the RICS/PDA/DEER pattern (bare model class registered directly in
  `experiment_configs.yaml`, generic `AutoForm`/`AutoModelWidget` renders it).
- Renamed the emission-waist parameter `R0` → `wem` (still `R(z) =
  wem·sqrt(1+...)` internally; only the `FittingParameter(name=...)` changed)
  to remove the registry collision at its source.
- Regrouped the 14 parameters into three `FittingParameterGroup`s —
  `MdfPhysical` (N, D, w0, wem, b, diam), `MdfOptics` (lam_ex, lam_em, n,
  pinhole, mag), `MdfOutputs` (Veff, conc, tauD) — each rendered as a
  `parameter_group_table` panel in `mdf.view.json`.
- Added `chisurf/core/models/fcs/relaxation.py::BunchingTerms`: zero or more
  `(ba_i, bt_i)` amplitude/time-constant pairs, added/removed through the
  same `dynamic_group` + `append_method`/`remove_method`/`rows_source` +
  `style:"table"` mechanism already used by TCSPC lifetimes/anisotropy
  rotations. Each term multiplies the diffusion shape by `(1 - ba_i + ba_i *
  exp(-tau/bt_i))`, matching the Parse-FCS catalogue's bunching convention.

## General composable FCS model

- `chisurf/core/models/fcs/general.py::GeneralFCSModel` — a `diffusion_mode`
  choice (`"mdf"` | `"gauss"` | `"two_focus"`, an AutoForm `choice` radio
  section) selects between reusing `MdfPhysical`/`MdfOptics`, a new
  `GaussDiffusion` group (classic single-focus 3-D-Gaussian PSF, absolute D),
  or a second `GaussDiffusion` instance preset for the classic Dertinger
  two-focus/dual-focus technique (`diam` unfixed and non-zero by default) —
  made a directly selectable, discoverable third option per explicit user
  request, rather than only a parameter buried in the Gaussian table. Every
  mode in fact supports the same two-focus cross-correlation term via `diam`
  (known inter-focus separation) — the Dertinger convention already used by
  the Parse-FCS catalogue's "Two-focus 3D diffusion" entry
  (`exp(-diam²/(w_r²+4Dτ))`); `diam = 0` is single-focus. The `"two_focus"`
  preset is the same `GaussDiffusion` class/formula, just a separate instance
  with a different starting `diam`.
- Added `relaxation.py::AntibunchingTerms` alongside `BunchingTerms`: a pure
  sub-Poissonian dip `(1 - aba_i * exp(-tau/abt_i))`, no plateau shift,
  matching the catalogue's antibunching convention.
- Normalization is `G(0) = b + 1/N` (matching `MdfFCSModel`) for both
  diffusion modes — a deliberate departure from the legacy catalogue's
  `1/(N·sqrt(8))` convention (a PAM-specific artifact); porting a catalogue
  `N` here means dividing by `sqrt(8)`.
- This supersedes the diffusion-x-bunching/antibunching combinatorial subset
  of `models.yaml` (`"3D Gauss, N bunching"`, `"... + antibunching"`,
  multi-diffusion+bunching combos) for new work. The catalogue itself is
  unchanged and remains the path for what `GeneralFCSModel` does not cover:
  flow, scanning FCS, FRET-FCCS, background/afterpulsing/bleaching
  correction terms (PRD-54 territory).

# Definition of Done

- [x] Registry generator emits `by_qualified_id` + `ambiguous`; `Parameter`
  lookup prefers `registry_id` → class-scoped → non-ambiguous bare name.
- [x] `parameter_registry.json` regenerated; Förster-radius `R0` description
  encoding fixed.
- [x] `MdfFCSModel` relocated to `core/models/fcs/mdf.py`, `R0` renamed to
  `wem`, regrouped into `physical`/`optics`/`outputs` tables + `mdf.view.json`.
- [x] `MdfFCSWidget` and its `mfw(...)` widget list deleted;
  `experiment_configs.yaml` / `main_helper.py` alias updated.
- [x] `BunchingTerms` (shared) added to `MdfFCSModel` via a dynamic table.
- [x] `GeneralFCSModel` added and registered as "FCS (general)", with a
  3-way `diffusion_mode` selector (MDF / Gauss / Two-focus) + bunching +
  antibunching term lists.
- [x] Tests: `test/fitting/test_parameter_registry_scoping.py` (scoping
  regression), `test/gui/test_fcs_models_resolve.py` (both models resolve),
  `test/gui/test_fcs_model_editor.py` (table rendering, bunching/antibunching
  add/remove, two-focus suppression, `wem`-not-Förster-radius guard).
- [x] `okf/plugins/fcs.md` and `okf/subsystems/parameters.md` updated;
  `docs/tutorials/05_enderlein_mdf_two_focus_fcs.md` cross-reference fixed.

# Follow-ups

- The Parse-FCS catalogue (`models.yaml`) is untouched; deciding whether to
  deprecate its now-superseded diffusion×bunching entries in favor of
  `GeneralFCSModel` is left to a future PRD.
- Several `registry_id=` strings across `mdf.py`/`general.py` (e.g.
  `"fcs_mdf.N"`) don't match the generator's actual `by_qualified_id` key
  format (`"MdfPhysical.N"`), so they never hit that index and silently fall
  through to the class-scoped frame-inspection step, which happens to resolve
  correctly anyway. Harmless (no wrong description, just a redundant lookup
  miss) but inconsistent; a broad rename to match the real convention (or
  changing the generator to also index the literal `registry_id` string) is
  unscoped cleanup, not tied to any open bug.

## 2026-07-24 follow-up (same-day UX polish)

First real use of `GeneralFCSModel` surfaced several rough edges, fixed in one
pass — this also **resolved the live-re-fold follow-up above** (previously:
"diffusion-panel fold state is computed once at editor build time ... a
live-rebuild-on-`call` wiring exists for at least one other tool-specific
AutoForm host; generalizing it to the model editor is a candidate follow-up"):

- **Live re-fold, `not_equals`, default mode.** `ChoiceSection` gained
  `rebuild_on_change` (deferred `AutoForm.rebuild()`, generalizing the
  tool-specific combo-driven rebuild pattern into `_BoundControlMixin`, scoped
  to `choice` sections only); `_collapsed_when` gained `not_equals`. Each
  diffusion panel now folds via `not_equals` its own mode, and the
  `diffusion_mode` choice sets `rebuild_on_change`, so switching modes
  live-re-folds the siblings — only the active mode's panel stays expanded.
  Default `diffusion_mode` changed `"mdf"` → `"gauss"`.
- **Bounds columns hidden by default everywhere.** `PanelSection.bounds_toggle`
  default flipped `False` → `True` (previously opt-in per panel, e.g. only
  TCSPC lifetime) — fixes the bunching/anticorrelation dynamic tables (many
  paired Lo/Hi/Bounds/Error columns) overflowing narrow docks.
  General framework change, not FCS-specific.
- **Decade-spaced relaxation defaults + rename.** `add_bunching`/`add_anticorr`
  default a new term's time constant to the next decade up (bunching: 1, 10,
  100 µs; anticorrelation: 1, 10, 100 ns) instead of a fixed value.
  `AntibunchingTerms` renamed `AnticorrTerms` (the legacy Parse-FCS catalogue
  keeps its own, older "antibunching" terminology unchanged); anticorrelation
  time constants now stored/labeled in ns (were ms — unreadably small at the
  real timescale).
- **Compound-equation display.** Both models gain an `equation_html()` method
  and a top "Equation" panel (`info` section, `source: "equation_html"`)
  rendering the currently active formula as HTML — the selected diffusion
  term (or the numerical `MDF_Enderlein(...)` placeholder for `"mdf"` mode)
  times each active bunching/anticorrelation factor, built from
  `BunchingTerms.equation_html()`/`AnticorrTerms.equation_html()` (new,
  mirroring their own `apply()` formula) so the text can never drift from
  what's actually computed.
- **Fixed: dynamic-group add/remove didn't refresh sibling `AUTOFORM_REFRESH`
  widgets.** Adding the equation panel surfaced a real, general `AutoForm` gap
  (not FCS-specific): `_build_dynamic_group`'s `on_add`/`on_del`/
  `on_add_table`/`on_del_table` only rebuilt their *own*
  `PairedParameterTableWidget`/row grid after dispatching the fit-update
  action — nothing called `self.refresh_plots()`, so any other
  `AUTOFORM_REFRESH` widget (the new equation panel, but also any status/info
  panel elsewhere) went stale after clicking "add"/"del" until something else
  forced a full rebuild. Fixed by adding `self.refresh_plots()` to all four
  handlers. Regression test simulates the real click
  (`test_clicking_add_bunching_button_refreshes_the_equation_panel`), not a
  direct model mutation, so it only passes if the button's own handler does
  the refresh.
- **`hidden_when`: fully hide, not just fold.** Folding the irrelevant
  diffusion panels (via `collapsed_when`) still left a header bar for each —
  explicit follow-up ask: "really hide the irrelevant groups". Added
  `PanelSection.hidden_when` (same `{target?, attr, equals|not_equals}` shape
  as `collapsed_when`) evaluated centrally in `AutoForm._emit_sections`
  (alongside the existing static `visible` field) rather than per section
  builder, so `setVisible(False)` sticks instead of being clobbered by the
  `widget.setVisible(bool(section.visible))` line that already ran there for
  every section. `general.view.json`'s three diffusion panels now use
  `hidden_when` instead of `collapsed_when` — only the active mode's panel is
  even present, not merely expanded.
- **Background-corrected outputs.** Baseline offset `b` default `0` → `1`
  (matches the typical normalized-ACF convention, e.g. Kristine data, where
  `G(∞) → 1`). Added a `bg` background-count-rate parameter (kHz, matching the
  catalogue's `Counts`/`BG` convention) to `MdfPhysical`/`GaussDiffusion`, and
  a derived `brightness` output (`mdf.py::compute_brightness`,
  `(CR_total − bg)/N`, `CR_total` from the data file's `mean_count_rate`
  metadata) shared by `MdfOutputs` and `GaussDiffusion`. `GaussDiffusion` also
  reports `s = w_z/w_r` as a derived output (still fits absolute `w_r`/`w_z`,
  not the dimensionless legacy parametrization).
- **Fixed a real, general precision/range bug in every parameter table**
  (explicit follow-up: "table para edit needs more sig digits, do not cut
  off"). `ParameterGroupTableWidget`/`PairedParameterTableWidget`'s value/
  Lo/Hi columns had no custom editor delegate, so Qt's default double-spinbox
  editor (2 decimals, 0–99.99 range) opened for them — a 0.001 ms bunching
  time constant displayed as "0.00" while editing, and a value above 99.99
  (e.g. `w_z[nm] = 2020.1`) could not even be typed. New `_FloatEditDelegate`
  (`chisurf/gui/autoform/sections/parameter_table.py`) wraps the same
  `ScientificDoubleSpinBox` (`%g` formatting, unbounded) the standalone
  per-parameter widgets already use, wired onto both table widgets' value/
  bounds columns in both `__init__` and `set_params` (so it survives a
  dynamic-group add/remove rebuild). Also fixed the brightness output's
  `label_text="&epsiv;[kHz]"` → `"&epsilon;[kHz]"` — Qt's rich-text engine
  only supports HTML4's Greek-letter entity set; `&epsiv;` (HTML5-only, the
  curly-epsilon variant) rendered as literal text instead of the glyph.

See [fcs plugin](/plugins/fcs.md), [parameters](/subsystems/parameters.md), and
[gui-autoform](/subsystems/gui-autoform.md).
