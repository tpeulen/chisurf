---
type: PRD
prd: "38"
title: "PRD-38: Model/UI Split — view-spec JSON drives auto-generated model editors"
description: Splits a fitting model's compute definition from its editor by describing the editor in a co-located JSON view spec that a generic GUI renderer turns into the control panel.
status: done
phase: "unassigned"
resource: chisurf/core/models/
tags: [prd, gui]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
PRD-38 makes a fitting model's editor the automatic result of its computational definition instead of a hand-written per-model widget that duplicates the model's structure and welds Qt to the compute side. Each model stays in one place (parameters plus `update_model` in `chisurf/core/models`, Qt-free), its editor is described in a hand-editable `<model>.view.json` file, and the GUI renders that spec by composition via `AutoModelWidget`. A strict, AST-CI-enforced boundary keeps `core/models/**` from importing any GUI toolkit, while a string-keyed registry provides an escape hatch for bespoke custom sections. The view-spec vocabulary has grown to parameter groups, dynamic groups, curve inputs, choices, toggles, and custom sections plus plots.

# Status
**Done.** Every registered fitting model is a pure, Qt-free compute model whose
editor is generated from a co-located `*.view.json`; no `.ui` file remains under
`models/`, no model declares `plot_classes`, and `chisurf/gui/widgets/models/` is
deprecation shims plus the generic renderer. The per-model record is the STATUS
TABLE below and the increment notes; what the machinery grew along the way is in
the [GUI & AutoForm](/subsystems/gui-autoform.md) concept, which is where to look
first from now on.

# STATUS TABLE — per-model screening

Ported means: the class registered in `chisurf/core/settings/experiment_configs.yaml`
lives under `chisurf.core.models.` and its editor comes from a `*.view.json`.

**The registration is the only proof.** A `view.json` can exist for a model nobody
can open, and a legacy widget file can be mostly dead while still exporting one
live class. Count registrations, not files. Re-derive with:

```bash
grep -n "chisurf.gui.widgets.models\|chisurf.core.models" \
  chisurf/core/settings/experiment_configs.yaml    # live registrations
find chisurf/core/models -name "*.view.json" | sort
grep -rho '"type": "parameter_group[a-z_]*"' chisurf --include="*.view.json" \
  | sort | uniq -c                                 # table-vs-verbose adoption
```

Tiers: **A** portable with existing vocabulary · **B** blocked — compute lives in
the GUI file, needs a pure-model extraction into `core/models/**` first · **C**
needs a new AutoForm section · **D** dead code.

| Experiment | Model | Ported | Tier | Blocked on |
|---|---|:--:|:--:|---|
| tcspc | `LifetimeModel` (`lifetime.view.json`) | ✅ | — | anisotropy r(t) diagnostics panel is the one un-ported control (tier C) |
| tcspc | `LifetimeMixtureModel` (`mix_model.view.json`) | ✅ | — | — |
| tcspc | `FRETrateModel` (`fret_rate.view.json`) | ✅ | — | anisotropy r(t) panel, shared with Lifetime |
| tcspc | `GaussianModel` (`fret_gaussian.view.json`) | ✅ | — | anisotropy r(t) panel, shared with Lifetime |
| tcspc | `WormLikeChainModel` (`worm_like_chain.view.json`), `SawNuModel` (`saw_nu.view.json`), `IsingChainModel` (`ising_chain.view.json`) | ✅ | — | — |
| tcspc | `PDDEMModel` (`pddem.view.json`) | ✅ | — | anisotropy r(t) panel, shared |
| tcspc | `FRETStructure` (`fret_structure.view.json`) | ✅ | — | anisotropy r(t) panel, shared |
| tcspc | `MaxEntLifetimeModel` (`maxent_lifetime.view.json`), `MaxEntFRETModel` (`maxent_fret.view.json`) | ✅ | — | — |
| tcspc | `ParseDecayModel` (`parse_decay.view.json`) | ✅ | — | equation validity badge + LaTeX preview not ported |
| tcspc | ~~`EtModelFree`~~ | — | D | **deregistered** — abstract, never openable; see [known issues](/references/known-issues.md) |
| fcs | `MdfFCSModel`, `GeneralFCSModel`, `FCSKineticsModel` | ✅ | — | — |
| fcs | `ParseFCSModel` (`parse.view.json`) | ✅ | — | as above |
| fcs | `DyeShapeFCSModel` (`dye_shape.view.json`) | ✅ | — | — |
| fcs | `MaxEntFCSModel` (`maxent_fcs.view.json`), `MaxEntRHModel` (`maxent_rh.view.json`) | ✅ | — | — |
| pda2c/pda3c | all 7 | ✅ | — | — |
| deer | all 4 | ✅ | — | — |
| ics | both | ✅ | — | — |
| mfd | `Mfd2DModel` | ✅ | — | — |
| pch | `PchMultiComponentModel` (`pch.view.json`), `FidaModel` (`fida.view.json`) | ✅ | — | — |
| pcf | `ParsePCFModel` (`parse.view.json`) | ✅ | — | as above |
| stopped_flow | `ParseStoppedFlowModel` (`parse.view.json`) | ✅ | — | it had **no catalogue and could not be constructed** at all; both fixed |
| stopped_flow | `ReactionModel` (`reaction.view.json`) | ✅ | — | it was **abstract** and could not be constructed at all; now it computes |
| structure | `ProteinMCModel` (`proteinmc.view.json`) | ✅ | — | — |
| global | `GlobalFitModel` (`globalfit.view.json`) | ✅ | — | — |
| global | `ParameterTransformModel` (`parameter_transform.view.json`) | ✅ | — | — |

**Tier D — dead code.** `gui/widgets/models/pda2c/widgets.py`: 9 of 10 classes are
unreferenced outside the file (~1,590 of 2,090 LOC), but `FretRdaAxisSettingsWidget`
(`:1047`) is live — `gui/main.py:1514` imports it. Relocate that one class, then
delete the rest; the file is **not** a wholesale delete, contrary to an earlier
reading of it. `gui/widgets/models/tcspc/lifetime_mix.py::LifetimeMixModelWidget`
is unregistered. The 5 stray `.ui` files that sat inside the Qt-free
`core/models/**` are deleted.

Final counts: 44 model classes across 12 families; **no legacy registration and no
`.ui` file** remains under `models/`. `gui/widgets/models/tcspc/` is down from ~5k
LOC to an alias module plus two helper files, `fcs/` is four shims totalling ~70
lines (from ~1,950), `proteinmc.py` is 26 lines (from 1,984), `pda2c/` is one
33-line `__init__` (from 2,090), and `parse/` is a shim plus the shared LaTeX
helper (from 1,022). `model_widget.py` is gone — it existed to give a
hand-written model widget a workable metaclass, and there are none.

# Goal
Make a fitting model's **editor the automatic result of its computational definition**. Maintain each model in one place (compute + parameters in `chisurf/core/models`), describe its editor in a **user-editable JSON file that accompanies the model**, and have the GUI render that editor generically. Eliminate the hand-written, per-model widget that today duplicates the model's structure and welds Qt to the compute side.

# Evidence (why)

Today model and widget are not split — they are the **same object** via multiple inheritance, and structure is declared twice:

- `class LifetimeWidget(Lifetime, QtWidgets.QWidget)` and `class LifetimeModelWidgetBase(ModelWidget, LifetimeModel)` (`chisurf/gui/widgets/models/tcspc/lifetime.py:45,319`). The widget *is* the model; compute and Qt live in one class.
- `Lifetime.append/pop/__init__` (`core/models/tcspc/lifetime.py:166,206`) define component structure; `LifetimeWidget.append/pop/update` (`gui/.../lifetime.py:287,311,48`) re-implement the *same* structure just to spawn/destroy a widget per parameter and copy values back with `for w, v in zip(...)`.
- `plot_classes` references GUI plot classes from inside the model-widget (`gui/.../lifetime.py:321`) — a hard GUI dependency on what should be model.
- `parameter_registry.json` exists because parameter metadata (label, bounds, description) is scattered across `__init__`s and has to be *scraped back out*.

Yet the pieces for "model declares, GUI derives" already exist and are unused by the hand-written models: a generic renderer (`FittingParameterGroupWidget`, `parameter_widgets.py:1658`), the `parameter.controller = widget` binding, and two declarative model factories (`function_to_model_decorator`, `tcspc.models.json`). This PRD generalises that path to all structured models and adds the missing **strict boundary** + **JSON authoring surface**.

Relationship: complements **PRD-23** (thin view-only widgets, construction smoke tests) and **PRD-26** (declarative generation from data). This PRD applies the same "declare once, generate the surface" principle to model editors.

# Design

Strict three-layer split with a one-directional dependency (`gui` → `core`, never the reverse):

1. **Compute (pure, `core/models/**`)** — parameters + `update_model`. No Qt. Enforced by an AST CI test, not convention.
2. **View spec (data)** — a `ModelView` tree of section/plot descriptors. Authored as a `<model>.view.json` file co-located with the compute model and meant to be hand-edited. The dataclasses are the *schema* that validates it. Custom UI and target parameter groups are referenced by **string**, never by a widget class.
3. **Presentation (`gui/**`)** — `AutoModelWidget(model)` builds the control panel by **composition** (has-a model). A registry maps string keys → concrete plot classes and bespoke section widgets.

Customisation is preserved without leaking Qt into the model: a section of type `custom` carries a `key`; the GUI registry owns the hand-written widget under that key (e.g. the lifetime amplitude options header, the link/read menus, the r(t) panel). Unlimited customisation, zero boundary violation.

## The boundary rule (enforced)

`chisurf/core/models/**` must never import `qtpy`, `PyQt5/6`, `PySide2/6`, or `chisurf.gui`. A stray import fails CI.

# API

Core (pure data; `core/models/view_spec.py`):

```python
ModelView(sections: tuple[Section, ...], plots: tuple[PlotSpec, ...])
Section subtypes: ParameterGroupSection, DynamicGroupSection, CustomSection
PlotSpec(key: str, options: dict)
load_view_spec(path | dict) -> ModelView        # JSON loader + validation
```

Model hook (`core/models/model.py`):

```python
class Model:
    view_spec_file: str | None = None   # co-located <name>.view.json
    def view_spec(self) -> ModelView    # loads file, else auto-derives
```

GUI (`gui/widgets/models/`):

```python
AutoModelWidget(model)                                  # renders the editor
sections.registry.register_plot(key, factory)
sections.registry.register_section(key)                 # decorator
sections.registry.resolve_plot_specs(view) -> [(cls, options)]  # legacy bridge
```

## JSON shape (`lifetime.view.json`)

```json
{
  "sections": [
    {"type": "parameter_group", "target": "convolve", "title": "Convolution"},
    {"type": "dynamic_group", "target": "lifetimes", "title": "Lifetimes",
     "row_width": 2, "header_keys": ["lifetime_amplitude_options"]}
  ],
  "plots": [{"key": "line", "options": {"y_label": "counts"}}]
}
```

`target` names a model attribute resolved with `getattr`; `key` resolves in the GUI registry. No code in the file.

# Tasks

1. View-spec vocabulary + JSON loader (`view_spec.py`), pure data. — DONE
2. AST boundary CI test for `core/models/**`. — DONE
3. `Model.view_spec()` JSON discovery + auto-derive fallback. — DONE
4. `lifetime.view.json`; `LifetimeModel.view_spec_file`; seed ≥1 component on the compute side. — DONE
5. `AutoModelWidget` + section/plot registry + builtin registrations. — DONE
6. Offscreen-Qt render/add-del tests + headless view-spec tests. — DONE
7. **Live wiring**: GUI builds `AutoModelWidget(fit.model)` instead of inheriting the model; `fit_subwindow` plots via `resolve_plot_specs(view_spec())` instead of `fit.model.plot_classes`; port link/read menus + r(t) panel to registered custom sections. — DONE
8. Migrate every structured model to `view.json`; delete their hand-written widgets. — DONE (all 44, across 12 families; see the STATUS TABLE)
9. Remove `plot_classes` from models once all consumers read `view_spec().plots`. — DONE (increment 20)
10. Codify the table-rendering default and the before/after migration rule. — DONE

# Definition of Done

All met.

- ✅ A registered model class instantiated by `Fit` carries no Qt; the editor is a separate `AutoModelWidget`. Project save/load and fitting are unaffected.
- ✅ Editing `lifetime.view.json` (reorder sections, retitle, add/remove a plot) changes the live editor with no Python change.
- ✅ Custom UI (amplitude options, link/read, r(t)) works, referenced by key.
- ✅ Boundary test green; per-model widget files for migrated models deleted — and with them the base class (`ModelWidget`) and the last `.ui` under `models/`.

# Definition of Clean

- No `for w, v in zip(widgets, values)` value copy-back; model is the single source of truth, controllers re-render via the existing binding.
- No model imports a plot/widget class. No widget subclasses a model.
- Parameter metadata (label/bounds/units) lives on the parameter constructor, sourced from `parameter_registry.json`; not duplicated in widgets.

# Implementation status

**Increment 1 (data spine + boundary) — DONE.** `core/models/view_spec.py` (dataclasses + `load_view_spec`), `Model.view_spec()` with `view_spec_file` discovery and auto-derive fallback, `test/architecture/test_model_ui_boundary.py` (AST check, green). `core/models/**` is already Qt-free and now locked.

**Increment 2 (Lifetime authored as JSON) — DONE.** `core/models/tcspc/lifetime.view.json`; `LifetimeModel.view_spec_file = "lifetime.view.json"`; the model seeds one lifetime component (a zero-component lifetime model is invalid). The hand-written Python `view_spec()` was removed in favour of the data file.

**Increment 3 (generic renderer) — DONE.** `gui/widgets/models/auto_model_widget.py::AutoModelWidget` (composition), `gui/widgets/models/sections/{registry,builtin}.py` (plot keys + the `lifetime_amplitude_options` custom header, `resolve_plot_specs` bridge).

**Tests — DONE.** Run in the `arm64` conda env with `-p no:cov -o addopts=""`:
- non-GUI: `test/models/test_view_spec.py test/architecture/` (3 pass).
- offscreen Qt: `QT_QPA_PLATFORM=offscreen ... test/gui/test_auto_model_widget.py` (4 pass). Must run in its own pytest process — mixing GUI and non-GUI modules segfaults at Qt teardown. Existing `test/fitting/test_models_regression.py` unchanged (its one failure, `ParseModel()` with no fit, predates this work).

**Increment 4 (live wiring) — DONE (seams + additive entry); custom-section ports pending.** The live app now routes every model through a compatibility seam, `gui/widgets/models/model_editor.py`:
- `build_model_editor(fit.model)` — returns the model itself when it is already a widget (legacy, unchanged), else an `AutoModelWidget`. Wired at `main.py` (`modelLayout.addWidget`).
- `model_plot_specs(fit.model)` — plots from `view_spec().plots` via `resolve_plot_specs` (with distribution-accessor resolution), falling back to `plot_classes`. Wired at `fit_subwindow.py:156`.
Because all currently-registered models are widgets, both take the legacy branch → zero behaviour change. A pure model `LifetimeModelAuto` (same compute as `LifetimeModel`, shares `lifetime.view.json`) is registered **additively** in `experiment_configs.yaml` as menu entry **"Lifetime (auto-UI)"**, so the data-driven editor can be opened live alongside the hand-written one. Verified headless end-to-end (resolve → Fit → pure model → `AutoModelWidget` + 6 resolved plots; full fit lifecycle: `update_model`/`get_curves`/`chi2r`/residuals). Test: `test_registered_auto_lifetime_model_wires_live`.

**Increment 4b (link/read menus) — DONE.** The lifetime read/link header controls were ported from `LifetimeWidget` into the registered `lifetime_amplitude_options` section (`gui/widgets/models/sections/builtin.py`), operating on **core** `Lifetime` groups (`group.link = target`, value-copy via the action dispatcher) so they work for both legacy and auto-rendered models. Offscreen test: `test_lifetime_header_has_read_link_controls`.

**Increment 4c (plot-reference modes to core) — DONE.** The overlay modes (total/peak photons, donor reference, r(t) anisotropy) were relocated **verbatim** (programmatic AST extraction, no hand-copying) from the widgets to core:
- core `Anisotropy` gained the 6 diagnostics helpers (`_shift_trace_to_reference`, `_fit_timeshift`, `_fit_bg_level`, `_curve_bg_level`, `_extract_vv_vh_raw_for_diag`, `_extract_vv_vh_model_for_diag`).
- core `LifetimeModel` gained the plot-reference block (`_tcspc_reference_window` … `get_plot_reference_modes`); core `lifetime.py` now imports `plot_transforms`.
The widget copies were removed; legacy widgets inherit the methods (verified: `LifetimeModelWidget`/`AnisotropyWidget` still construct and expose the same 3 modes; all TCSPC model widgets import; `EtModelFreeWidget` never had them, no regression). Boundary test still green (the moved code is Qt-free), regression unchanged, and the pure `LifetimeModelAuto` now exposes `get_plot_reference_modes()` headless.

**Increment 4d (code view opens model + view.json) — DONE.** The fit window's plot↔code toggle (`FitSubWindow.show_code_view`) now also lists the model's `*.view.json` in the file picker and opens it as a second editor tab next to the model source (`CodeEditor.open_file` is tab-based and detects JSON), so "Code" shows both the computation and its editor layout. Resolver: `source_jump.resolve_model_view_spec_path`. Test: `test_code_view_resolves_model_view_json`.

**Increment 4e (code view targets the COMPUTE class, not the widget) — DONE.** Screenshot bug: for a *legacy* `LifetimeModelWidget`, "Code" opened the GUI widget `.py` (and missed the json) because `show_code_view`/`save_model_code` used `self.fit.model.__class__` — the widget. Added `source_jump.resolve_compute_model_class` (walks `type(model).__mro__`, returns the most-derived `core.models.model.Model` subclass that is **not** a Qt widget). `show_code_view` now opens `core/models/tcspc/lifetime.py` + `lifetime.view.json` for both legacy and pure entries. `save_model_code` resolves/reloads the compute module and only hot-swaps `instance.__class__` when the live object *is* the pure compute model (swapping a widget's class to the pure model would strip its Qt behaviour). Test: `test_code_view_legacy_widget_resolves_to_compute_model`.

**Increment 5 (first flip attempt) — DONE, THEN REVERTED, NOW REDONE (see increment 8).** This increment claimed the primary entry was flipped and the demo class deleted. That was **reverted** at some point without being recorded here: for most of this PRD's life `experiment_configs.yaml` registered the hand-written `LifetimeModelWidget` as "the proven daily driver" with `LifetimeNewModel` alongside it as "Lifetime (new)". Increment 8 flipped it for real. *Lesson: a reverted increment must be written down here, or the PRD reports a state the tree does not have — and the next session plans against fiction.* **`gui/widgets/models/tcspc/lifetime.py` was NOT deleted**: it still defines the *shared bases* `LifetimeWidget` and `LifetimeModelWidgetBase` (and `LifetimeMixtureModelWidget`) that the FRET/Gaussian/PDDEM/WLC/fret_rate/lifetime_mix widget family inherits. That file shrinks to its real size only once that family is migrated (task 8). Verified headless: dependent widgets still import; pure `LifetimeModel` → `Fit` → `AutoModelWidget` + 6 plots; 11/11 GUI + 3 boundary/view-spec tests green; models-regression unchanged (1 pre-existing `ParseModel()` failure).

**Increment 5b (flip fallout fixes, found by live GUI run) — DONE.** Running the flipped app surfaced two regressions, both fixed:
- *"Lifetime" missing from the model combobox.* The user copy `~/.chisurf/experiment_configs.yaml` **replaces** (not merges) the default model list and still pinned the deleted `...gui.widgets.models.tcspc.LifetimeModelWidget`, which resolved to `None` → entry dropped. Fix: a back-compat **alias** `LifetimeModelWidget = LifetimeModel` in the widget module (+ `__init__` re-export). Old configs/pickled projects now resolve to the pure model (GUI builds an `AutoModelWidget`). *General rule: deleting a registered model class needs a deprecation alias — user configs and projects pin class paths.*
- *`Failed to load view spec 'lifetime.view.json' for FRETrateModelWidget`.* The FRET/Gaussian/etc. widgets inherit `view_spec_file` from `LifetimeModel`, and `Model.view_spec()` resolved it against `type(self)`'s module (the FRET widget's dir). Fixes: (a) `Model.view_spec()` resolves `view_spec_file` against the **declaring** class's module (MRO `__dict__` walk); (b) `model_plot_specs()` now returns `plot_classes` directly for any `QWidget` model, so a legacy widget never inherits the lifetime view-spec's plots and `view_spec()` isn't consulted for widgets at all. Tests: `test_lifetime_model_widget_is_backcompat_alias`, `test_legacy_widget_does_not_inherit_lifetime_plots`.

**Increment 5c (real runtime wiring — the model panel) — DONE.** The flip crashed live: `add_fit failed ... addWidget(): argument 1 has unexpected type 'LifetimeModel'`. Increment 4 wired the seam at `main.py modelLayout.addWidget`, but the **actual** runtime add-fit path is `macros/core_fit.py::add_fit` (`gui.modelLayout.addWidget(fit.model)`), which was never routed through the seam — and several sites manipulate `fit.model` as a widget. Fixes:
- `model_editor.py` gained editor **caching + lifecycle helpers**: `build_model_editor` now caches the `AutoModelWidget` on the model (`_chisurf_model_editor`, an underscore attr → skipped by view-spec auto-derive, not pickled), with an `_is_alive()` guard so a layout-cleared (deleted) editor is rebuilt rather than reused. New `model_editor_widget` / `show_model_editor` / `hide_model_editor`.
- Wired the real sites: `core_fit.py` add (`addWidget(build_model_editor(fit.model))`), fit-switch show/hide (`show/hide_model_editor`), and the two report screenshots (`model_editor_widget(...)`, skip if `None`); `main.py:412 subWindowActivated` (`show_model_editor`). Post-fit value refresh needs no new wiring — `Model.update()`/`finalize()` are pure-core and propagate to the bound controllers.
- `Model.update()` now skips parameter groups without an `update()` method (a GUI-widget-only method) instead of logging a warning every fit iteration.
Tests: `test_add_fit_display_path_wires_pure_model` (+ existing 13). Verified headless: pure model → build editor → `addWidget` → `update`/`finalize`/`rebuild`, no crash, no per-iteration warning spam.

**Increment 6 (curve inputs + empty-group fix + test path) — DONE.** The live GUI exposed that convolve/generic/corrections/anisotropy sections rendered empty and the flipped model "did not compute". Two causes, both fixed:
- *Empty sections:* those groups define parameters as plain attributes (`self._dt = FittingParameter(...)`) that only surface in `parameters_all` after `find_parameters()`. `AutoModelWidget._build_parameter_group` now calls it when the list is empty, so the ~11 convolve params (etc.) render.
- *No way to compute (curve inputs):* these groups need a **data curve** (IRF, background, linearization table), not scalar parameters. Per the chosen direction, the view-spec vocabulary was **extended** with a first-class `CurveInputSection` (`view_spec.py`: label, select_action, unload_action, index_key, name_key, name_attr; `curve_input` in `_SECTION_TYPES`). The GUI renders it via one generic `CurveInputWidget` (`sections/builtin.py`): an `ExperimentalDataSelector` whose selection dispatches `select_action` with `{index_key, name_key, fit_index}` then `fit.update`, with an optional unload. `lifetime.view.json` now declares the **IRF** input (`model.change_irf`/`model.unload_irf`) and the **linearization table** (`model.set_linearization`/`model.unload_lintable`). *Gap:* generic background has no clean set-action (the old widget set `_background_curve` directly) — it needs a new `model.set_background_curve` action before becoming a curve_input.

**Testing path established (user mandate).** "I do not want to test all changes manually." Added `test/gui/test_model_editor_integration.py` — a headless end-to-end smoke test that walks the real path (resolve model by name from config → build `Fit` → `build_model_editor` → every section populated → IRF present → model computes a finite decay); each assertion maps to one of the GUI bugs this increment fixed. Codified as the **`/test-model-editor` skill** (`.claude/skills/test-model-editor/SKILL.md`): run order, env gotchas (arm64, `-p no:cov`, offscreen-own-process, cosmetic teardown segfault), and the rule to extend the integration test when adding a model/section. Pure-data `CurveInputSection` round-trip lives in `test/models/test_view_spec.py`.

**Increment 7 (choice/toggle vocabulary) — DONE.** Gaps were enumerated by *self-inspected offscreen screenshots* of the editor (not by the user). Added two more first-class section types: `ChoiceSection` (enum combo, attr- or action-bound) and `ToggleSection` (bool checkbox). One generic `ChoiceWidget` / `ToggleWidget` (`_BoundControlMixin`) sets the bound attribute on the target group (or dispatches an action) then triggers a fit update; option lists may be inline or from a named source (`window_function_types`). `lifetime.view.json` now declares: convolution **type** (`convolve.mode`), **do-convolution**, the linearization **smoothing** window (`corrections.window_function`), the **pile-up / DNL / reverse** correction toggles, and the **polarization** type (`anisotropy.polarization_type`). Verified by screenshot + write-through tests. Vocabulary is now: `parameter_group`, `dynamic_group`, `curve_input`, `choice`, `toggle`, `custom`, plus plots.

**Increment 8 (the real flip, verified by before/after parity) — DONE.** The three "remaining parity gaps" listed by increment 7 were re-measured against the running editors rather than trusted, and two of the three were already closed:

- anisotropy **rotation add/remove** — already done: core `Anisotropy` has `add_rotation` (`anisotropy.py:278`) and `remove_rotation` (`:315`), which `lifetime.view.json` already referenced.
- convolve **FWHM** read-only — already rendered by the IRF `curve_input` widget itself. No section needed.
- generic **background curve** — genuinely missing, now added: `macros.model.set_background_curve` + the `model.set_background_curve` action + a `curve_input` in the Generic panel.

**A fourth gap the before/after comparison found that no one had listed:** the
`#PhB` / `#PhF` photon-count displays. They are computed `@property` values
(`Generic.n_ph_bg` / `n_ph_fl`), not `FittingParameter`s, so
`parameter_group_table` correctly skips them and they had silently vanished from
the AutoForm editor. Added as `value` sections with `read_only: true` to **both**
`lifetime.view.json` and `mix_model.view.json`.

**A latent bug found on the way.** `macros.model.unload_background_curve` read
`f.model.nuisance` — the group is `generic` — so it raised `AttributeError` into a
bare `except: pass` and the `model.unload_background_curve` action had **never
worked**. Fixed, and the dataset-resolution logic shared with `change_irf` was
factored into `_resolve_selected_curve` rather than duplicated.

The flip itself: `experiment_configs.yaml` registers `LifetimeModel` and
`LifetimeMixtureModel`; the additive "(new)" entries are gone;
`LifetimeModelWidget`, `LifetimeMixtureModelWidget`, `LifetimeNewModel` and
`LifetimeMixtureNewModel` are **deprecation aliases** of the pure models (user
config copies *replace* the model list and pickled projects pin class paths — a
path resolving to `None` drops the menu entry silently). ~215 lines of widget code
deleted; `LifetimeWidget` / `LifetimeModelWidgetBase` deliberately kept because
the FRET family still inherits them.

`LifetimeModel.name` was `"Lifetime "` — with a trailing space — which mattered
once the primary entry is matched **by name**: `macros/core_fit.py` compared
`mn == model_name` exactly, so a caller passing `"Lifetime"` fell through to a
global subclass scan and resolved by luck. Name fixed and the comparison made
whitespace-tolerant.

Blast radius worth knowing: `"Lifetime (new)"` had become a de-facto API string
across **13 test files** (agent, server, fitting-client suites). All updated.

**Remaining Lifetime parity gap (one, tier C):** the anisotropy **r(t)
diagnostics panel** — `gui/widgets/models/tcspc/anisotropy.py:95`
`_show_anisotropy_decay_dialog`, with its live-recompute r(t) spin boxes, l1↔l2
link toggle, CSV export and consistency label. The parity diff names the missing
controls exactly: `show r(t)`, `vv/vh diag`, `vv bg-corr`, `vh bg-corr`,
`diag: green (δ=…)`. It needs a new registered custom section; the nearest
existing is `decay_conv`.

**Increment 9 (the TCSPC FRET family, first two) — DONE.** `FRETrateModel`
("FRET: FD (Discrete)") and `GaussianModel` ("FRET: FD (Gaussian)") are now
described by `fret_rate.view.json` / `fret_gaussian.view.json`; their widgets are
deprecation aliases. What the port needed beyond existing vocabulary:

- **A `kappa2_controls` custom section.** The κ² mode radios, the fast-convolution
  toggle and the three dialog buttons (show κ², compute κ², calc R0) are not
  parameters, so no declarative type fits. The section *reuses*
  `kappa2_helpers.setup_kappa2_controls` — the same implementation the remaining
  hand-written FRET widgets call — so the two paths cannot drift. That helper
  grew an optional `fret_model` argument because a generated editor's owner is
  the section widget, not the model; it defaults to the owner, so every existing
  call site is unchanged.
- **Row sources and labels in core.** `Gaussians` and `DiscreteDistance` gained
  `_gaussian_parameter_rows` / `_distance_parameter_rows` (the
  `_lifetime_parameter_rows` contract), no-argument `append_gaussian` /
  `append_distance` for the add button, and `clear()`. Their parameters were
  created with a `name` but **no `label_text`**, which the hand-written editor
  did not care about and the parameter table does: the distances table first
  rendered as four nameless `Value / Fixed / Error` column groups. *A screenshot
  caught that; the control-inventory diff could not, because a missing column
  header is not a missing control.*
- **Seeding one component.** Both models now seed one distance for the reason
  `LifetimeModel` seeds one lifetime — a zero-component distribution has nothing
  to convolve, so the editor opened on an empty table. That broke three
  FRET-line tests, because two callers appended onto what they assumed was an
  empty container and silently got n+1 components with their values on the wrong
  one. Fixed at the callers (`fret_line.py` clears first;
  `fret_line/core/algorithms.py` now drives the container to *exactly*
  `n_components`) rather than by dropping the seed — the coupling to a
  constructor detail was the actual defect.

`datatools.first_distribution_pair` was added so the distance-distribution plot
accessor is a name a JSON spec can reference instead of a lambda.

**Increment 10 (the rest of the FRET family) — DONE.** `WormLikeChainModel`,
`SawNuModel`, `IsingChainModel` and `PDDEMModel` are described by JSON; their
widget modules are deprecation aliases (~490 lines of Qt deleted). The four specs
were *generated from* `fret_gaussian.view.json` so the shared
Convolution/Generic/Corrections/Anisotropy panels are identical by construction
rather than by four hand-copies that drift.

Three framework gaps had to be closed first, each of which had been failing
silently:

- **A section could not bind to a model-level attribute.** `_BoundControlMixin._group`
  returned `None` when a section declared no `target`, so a `toggle` for the
  worm-like chain's dye-linker switch rendered, accepted clicks and wrote them
  nowhere. An omitted target now means *the model itself*.
- **`fitting_parameter` rejected the option name its own dataclass declares.**
  `FittingParameterSection` declares `label`; the widget's keyword is
  `label_text`, and passing the declared name raised
  `unexpected keyword argument 'label'`. `AutoForm` logs that and skips the
  section, so the Chain panel shipped with its toggle and *none* of its three
  parameters. The factory now maps `label` → `label_text`.
- **Parameters with no `label_text` produce nameless table columns.** The same
  defect as the FRET distances, in `PDDEM`: the hand-written widget supplied
  those labels from the GUI side, so the core parameters had none and the table
  drew `Value / Fixed / Error` ten times over. Moved onto the parameters.

Two component groups also rendered empty because nothing seeded them
(`PDDEMModel.fa` — `fb` is the donor and *was* seeded, which is why only half the
editor looked wrong — and PDDEM's own `Gaussians`). Both now seed one component.

**A legacy labelling bug is deliberately not reproduced.** The old PDDEM widget
labelled `_alpha_B` as α(A→B) and `_alpha_A` as α(B→A), while the model documents
`alpha_A` as the A→B efficiency and `alpha_B` as B→A. The two transfer
efficiencies were shown swapped. The generated editor labels them to match the
model, so the parity diff shows a deliberate difference here.

**The guard that would have caught all of it** is now
`test_json_described_model_editor_builds_every_section` in
`test/gui/test_model_editor_integration.py` — parametrized over every
JSON-described TCSPC model, it asserts that **no section was skipped** (by reading
the ERROR log `AutoForm` emits and carries on from) and that every `min_rows`
component group actually has a component. Verified to fail by injecting a bad
option into a spec. *Add a model to `JSON_DESCRIBED_TCSPC_MODELS` when you
migrate it.*

The two MRO tests in `test_auto_model_widget.py` no longer name a model: they
discover a still-legacy widget from the config and skip when none remains.
Naming one meant repointing the test at every migration, which is how both ended
up asserting against classes that had become aliases.

**Increment 11 (MaxEnt ×2 + structure fit) — DONE.** `MaxEntLifetimeModel`,
`MaxEntFRETModel` and `FRETStructure` are described by JSON. Three findings worth
keeping:

- **The MaxEnt models were already sampling an L-curve that nothing displayed.**
  `compute_l_curve` cached weights, misfit and solution norms plus a detected
  corner in private arrays; the hand-written editor showed none of it. A core
  `l_curve` property now exposes them as the shared
  `chisurf.core.math.regularization.LCurveData`, and the spec renders it through
  the existing `lcurve` section — the reusable component had, until now, **zero**
  consumers among the models.
- **`FRETStructure` is tier A, not tier B.** It looked like a boundary inversion
  (`append` reads ten `res_*`/`linker_*`/`radius1_*` attributes that the widget
  defines as properties over a Qt `AVProperties`), but core's `__init__` sets all
  ten with the same defaults — the earlier reading tested the *class* rather than
  an instance and was wrong. The pure model is self-contained.
- **Four AV controls in the old editor did nothing at all.** `Resolution`,
  `Radius 2` and `Radius 3` were bound to the widget's `AVProperties`, and
  `FRETStructure.append` never passed them to `ACV` — which does accept and use
  them. They are wired through now, so setting them finally has an effect.
  `Initial Sphere` (and the AVProperties `min`/`max`) have no core counterpart
  and are deliberately not carried over.

Loading the PDB ensemble is declarative: `structure_files` is a core property
whose setter rebuilds the ensemble, so the `path_list` section — which writes the
attribute and calls `update()` — replaces the folder line-edit and file dialog
with no GUI code, and picks up the MMFDB "select from database" button every
`path_list` gets for free.

**A third framework asymmetry closed.** `AutoForm._resolve_group` treated an
omitted `target` as unresolvable, the same defect as `_BoundControlMixin._group`
in increment 10 but on the other resolver — so *some* section types could address
the model itself and others could not. Both now agree: **no target means the
model**, which is what a model holding its own parameters (FRETStructure's
per-structure fractions) needs.

**Increment 12 (the parse family — and the new section was not needed) — DONE.**
`ParseDecayModel`, `ParseFCSModel`, `ParsePCFModel` and a new
`ParseStoppedFlowModel` are described by JSON. The prediction that this needed an
`equation_catalogue` section was **wrong**: once the catalogue moved into core the
editor is ordinary vocabulary —

- `choice` with `options_source: "catalogue_names"` writing `model_name`, plus
  `rebuild_on_change` (a different equation has different parameters, so the table
  must be *rebuilt*, not refreshed);
- `value` (`kind: "str"`) on `func`;
- `info` with `source: "description"`;
- `parameter_group_table` with `parameters_source: "_parameters_equation"`.

What the move actually required in core (`ParseModel`): `catalogue_file` +
`catalogue_path`, lazy `catalogue`, `catalogue_names`, a `model_name` property whose
setter sets the equation *and* the initial values, `description`, and
`apply_initial_values`. `_models` had been a dict nothing ever filled — the Qt
widget owned all of it, so picking a model was not something a script or a view
spec could do.

**Initial values are seeded at parse time, not applied afterwards.** Any re-parse
rebuilds the parameter objects, and building the editor triggers one — so values
applied after selection were silently replaced by 1.0 and the table opened on
defaults the catalogue had overridden (`Mode` showed 1 where the catalogue says
20). Seeding inside `parse_code` makes the result independent of who re-parses,
and when.

**Two resolver fixes that remove a recurring silent blank.** `info`'s `source` and
the new `parameters_source` demanded a *method*; naming a property or a list
rendered an empty box / dropped the whole table, with at most a warning. Both now
accept a method **or** an attribute, and log when the name resolves to nothing.
This trap had already been recorded once as a known gotcha — worth fixing at the
resolver rather than per model.

**Two registered models turned out to be unopenable, not merely un-ported.**
`ParseStoppedFlowWidget` passed a `str` where a `pathlib.Path` was expected *and*
pointed at `settings/stopped_flow.models.json`, which is not in the tree — it
raised `AttributeError` on construction. It now has a core model and the
catalogue it never had (`core/models/stopped_flow/models.yaml`, the standard
relaxation forms). `EtModelFreeWidget` is registered and **abstract** (no
`update_model`), so selecting it can only fail; recorded in known-issues.

**Not ported:** the equation field's validity badge and LaTeX preview
(`ParseFormulaWidget` in `gui/widgets/models/parse/widget.py`). That file is
therefore *kept*, not deleted — it is now reachable only from its own `__init__`
and one test. `gui/widgets/models/parse/latex.py` stays regardless: it is used by
`equation_editor` and `expression_input`.

**Increment 13 (global fit) — DONE.** `GlobalFitModel` is described by
`globalfit.view.json` and `globalfit.ui` is deleted. The shared
`global_parameter_table` — built, tested and until now used by **nothing** — is its
parameter view, so the editor shows every parameter of every fit plus the
registered out-of-fit groups with Owner and Link columns, which is strictly more
than the hand-written table did.

`button_row`'s `action` is a **zero-arg model method**, not a dispatcher action, and
the existing `model.*` actions all need arguments (`row`, `parameter_name`). So core
gained the state the buttons read (`new_global_parameter_name`,
`selected_local_fit`, `selected_candidate_fit`, `candidate_fit_names`) and four
zero-arg methods over it. The editor therefore holds no state of its own — the
selection lives on the model, which is what let the list, the picker and the buttons
all be generic sections.

`ParameterTransformWidget` is **not** aliased alongside it: that model is still
hand-written, and its catalogue holds Python `code:` rather than an equation, so
`ParseModel`'s catalogue does not fit it.

*Guard note:* a **container** model computes nothing until it has members, so
"produces a finite curve" is wrong for it. The parametrized guard now asserts
finiteness always and non-emptiness only when the model actually has inputs.

**Increment 14 (delete the hand-written TCSPC layer; parameter transform) — DONE.**
`ParameterTransformModel` is described by `parameter_transform.view.json` and its
`.ui` is deleted. Its catalogue holds a Python `code:` block rather than an
`equation:`, which turned out to be **two class attributes**
(`catalogue_source_key`, `catalogue_target_attr`) rather than a second
implementation: the catalogue machinery moved out of `ParseModel` into
`chisurf/core/models/catalogue.py::EquationCatalogueMixin`, and both models use it.

The mixin creates its state **on first use** rather than in an `__init__`: it is
mixed into models with their own constructors and their own `__getattr__`, so
depending on a cooperative `super().__init__` chain raised `AttributeError` on the
first catalogue access for a host that did not call it.

Two things this model does not share with the others, both worth knowing before
writing a spec against a model that is not a decay: its parameters live on the
transform node (`_parameters`), not in `parameters_all` — so
`apply_initial_values` falls back to naming them from whatever list the model does
expose — and it has **no `y` at all**, being a parameter-to-parameter map. The
parametrized guard now skips the curve assertions for a model without `y`, and
treats an empty curve as correct only for a *container* model with no members.

Four `.ui` files gone in this increment. Two remain, each with one named blocker.

**Increment 15 (the anisotropy r(t) diagnostics, ported) — DONE.** The panel that
was lost with the widget layer is back as a registered section,
`anisotropy_diagnostics`, declared in the Anisotropy panel of **all ten** specs that
have one. It restores every control the old dialog had: the **VV/VH diag** toggle
over the two background-corrected integrals, and **show r(t)** with g / l1 / l2 /
BgVV / BgVH / dVH-VV as live spin boxes, the l1↔l2 link, Reset, and CSV export of
data and model on their own time axes.

Three things changed in the porting rather than being copied:

- **The window is modeless.** The original called `exec_()`, which blocks the event
  loop — and on an offscreen run blocks it with nobody able to close the window,
  which is also why nothing headless could ever screenshot it. It is a
  `QtCore.Qt.Window` shown with `show()`, held by a reference so it is not collected.
- **The anisotropy algebra moved to core** as
  `Anisotropy.rt_from_channels(t, vv, vh, g, l1, l2)`. It was a closure inside the
  dialog, so the numbers the plot drew could not be asserted without a display. It
  returns `None` for the anisotropies when the mixing matrix is singular rather than
  zeros, which would look like data.
- **CSV export pads instead of interpolating.** Data and model have independent time
  axes; resampling to share one would write numbers the fit never computed.

Verified headless by driving the window directly: four curves, both axes populated,
l1→l2 tracking while linked, l2 independent when unlinked, Reset restoring the
fit's factors — and by reading the screenshot.

**Increment 16 (PCH extractions) — DONE.** `FidaModel` and
`PchMultiComponentModel` are in `core/models/pch/`, and the four numpy functions
the latter computes with (`compute_p1`, `pch_single_species`, `pch_open_system`,
`pch_mixture`) moved to `core/models/pch/pch.py` — they were defined in a Qt
module, so a PCH distribution could not be evaluated or checked against a
reference without importing the GUI.

**What made these tier B was one pattern, and it is the thing to look for in the
rest**: a computed output written through `get_fitting_client()` from inside
`update_model` (or from `add_component`), wrapped in a bare `except`. It does
nothing whenever the client is absent — headless, or before the editor has
registered the fit — and says nothing about it. FIDA's mean, PCH's component
defaults, and (still un-extracted) the dye-shape model's D / tauD / cpm are all
this. The fix is a direct parameter write; the parameter's own controller binding
repaints it.

Also fixed here, affecting fifteen *other* specs: Qt reads `&` in a widget's text
as a mnemonic marker, so a panel titled "Background & totals" rendered as
"Background _totals". Titles are escaped at the renderer now.

**Increment 17 (the FCS extractions, and a sweep that had always returned NaN) — DONE.**
`DyeShapeFCSModel`, `MaxEntFCSModel` and `MaxEntRHModel` are in `core/models/fcs/`
(`dye_shape.py`, `maxent_models.py`) and described by JSON. Three findings:

- **The same fitting-client pattern increment 16 named, twice more.** Dye-shape's
  `D` / `tauD` / `cpm` / `cpm_all` were published through `get_fitting_client()`
  inside a bare `except`, so all four stayed **NaN** whenever the client was
  absent — which the legacy baseline screenshot shows plainly, four yellow
  `nan` fields in a shipped editor. They are direct parameter writes now.
- **The L-curve was NaN for every fit that had just been opened.** `Fit` starts
  with `xmax == 0`, which is an *empty* window rather than a full one, and the
  misfit norm of an empty window is NaN — so the entire sweep came back NaN, no
  corner could be detected, and the plot drew nothing until the user happened to
  set a fit range. The models read a degenerate window as the whole curve
  (`_fit_window`). *This is why "the L-curve is there" was never evidence that it
  worked.*
- **The bespoke L-curve plot and its controller are gone (≈400 LOC).** Instead of
  re-authoring them, the shared `lcurve` section grew what they had: a sweep
  window (min/max/N), a **sweep** button bound to `compute_action`, a **corner**
  button, and click-to-adopt bound to `select_action` — nearest point measured in
  *decades*, because on log axes the low-misfit end otherwise swallows every
  click. Every regularized model gets those controls by declaring one section.
  Porting it also took `LCurveWidget` off raw pyqtgraph onto chiplot and struck
  `maxent_widget.py` from `test/chiplot_native_allowlist.txt`.

Two smaller things: `datatools.distribution_pair` is the **identity** accessor a
distribution plot needs when the model attribute already *is* the `(density, axis)`
pair (JSON cannot hold the lambda the legacy spec used), and
`regularization.discrete_lcurve_corner` no longer calls `np.cross` on 2-D vectors,
which NumPy 2 deprecates.

The dye-shape model also stopped importing `chisurf.plugins.fcs.fcs_calculator`
for its Stokes-Einstein helpers — those are thin wrappers over
`core/fluorescence/diffusion.py`, so core now calls core.

**Increment 18 (the reaction scheme — and the system under it had never run) — DONE.**
`ReactionModel` is in `core/models/stopped_flow/reaction.py` with
`reaction.view.json`, `reaction.ui` is deleted, and the last stopped-flow
registration is a pure model. `ReactionWidget` was **abstract**, so there is no
before-image and functional compatibility was the bar.

Everything the `.ui` offered is declared, with no new section type:

| the old widget | how it is declared |
|---|---|
| per-species concentration + brightness | `parameter_group_table` with `row_width: 2`, `slot_labels ["c","Q"]` and `row_labels_source` |
| the reaction list | `table` over `reaction_rows` with `selected_attr` |
| add / remove / clear | `button_row` over three zero-arg model methods |
| reactions pasted as JSON | `value` `kind: "text"` bound to a `reaction_json` property |
| scaling / background / timeshift | `parameter_group_table` |
| autoscale | `toggle` |

**Deliberate difference:** the fit range is *not* reproduced. The old widget
embedded a whole `FittingControllerWidget` inside the model panel, duplicating the
fit window's own control; only the `autoscale` toggle that *reads* that range is a
model setting.

**`ReactionSystem` itself had four defects, none of which a construction test could
see** — the model above is its first real caller, because the widget that used it
could never be opened:

- **`reactions` returned a `zip`.** `odeint` calls `rate_equation` once per step
  with that same object, and a `zip` is exhausted after the first call — so every
  later derivative was zero and the concentrations never left their initial
  values. *Every reaction system integrated to a flat line.* It returns a list now,
  and the guard asserts an `A ⇌ B` system relaxes to the analytic `k_f/k_r`
  equilibrium rather than merely "computing something".
- **`n_species` raised `NameError`** — `reduce` was never imported and the
  `except` only caught `TypeError`.
- **`species_brightness` could not round-trip a list of numbers**: the setter
  stored what it was given, the getter read `.value` off each entry.
- **`plot()` called a matplotlib alias the module never imported**, so it raised
  `NameError` on every call. Deleted rather than fixed — a core maths module does
  not plot, and the model's editor already does.

Rate constants are `FittingParameter`s now (they were plain `Parameter`s, i.e. not
fittable — the hand-written editor hid this by appending its own widget-backed
parameters instead of calling `add_reaction`), and
`chisurf.core.models.stopped_flow` re-exports `ReactionSystem`, which is the import
path every doctest in the module already used and which did not exist.

**Increment 19 (ProteinMC — the last extraction) — DONE.** `ProteinMCModel` is in
`core/models/structure/proteinmc_model.py` with `proteinmc.view.json`;
`gui/widgets/models/proteinmc.py` is 26 lines of deprecation shim, from 1,984.

**What made this one tier B+C was that none of it could be reached from Python.**
The sampling settings lived in a modal dialog, each energy term's parameters in a
second one, and the run in a Qt worker with two throttling timers and a progress
dialog — so ProteinMC could only be run by clicking, and nothing about it was
assertable without a display. The model owns that state now and runs the sampler
in a plain `threading.Thread`, which is what let the widget-driven tests become
model tests.

The two "new sections" the table predicted turned out to be one new section and
one existing one:

- **the per-row settings table is an ordinary `table`.** `TableSection` already
  has `editable` + `update_call(row, column, value)` + `selected_attr`, so the
  energy terms are one table (Term / Eval. every / Weight, selection driving
  which term is being configured) and the selected term's own parameters are a
  second table below it. *Not* `state_table`, which binds plain float lists —
  these are heterogeneous per-term dicts, and each setting keeps the type of its
  default so a text cell cannot deliver `"True"` to the runner.
- **`background_run` is the new one, and it is general.** A model exposes two
  zero-arg methods (`start_action` / `stop_action`) and up to three read-only
  attributes (`running_attr`, `progress_attr`, `status_attr`); the section owns
  the start/stop buttons, the bar, the status line **and the timer**. Throttling
  the repaint is the reason a timer is right rather than a signal per frame: the
  plots redraw in O(frames) and a sampler emits far faster than a screen
  refreshes. That is the general form of the two hand-rolled throttles the widget
  had.

Also here: the three ProteinMC plots are registered plot **keys**
(`proteinmc_structure` / `proteinmc_network` / `proteinmc_traces`) so the spec can
name them; the distance-network plot read `model.labeling_edit.text()` — a line
edit — and reads `model.labeling_file` now; and the distances themselves were the
`get_fitting_client()`-in-a-bare-`except` pattern once more, so they were NaN
headless.

**A defect in the parity helper itself, found by using it.**
`migration_parity.capture()` expanded folds by clicking checkable `QToolButton`s,
but AutoForm's `CollapsibleBox` header is a `QPushButton` — so **every panel a
spec declares `collapsed` stayed shut**, in both halves of every pair taken with
it, and its controls were missing from the control inventory too. That is exactly
the loss the module exists to catch. Fixed to call `CollapsibleBox.set_expanded`.

*Guard note:* `_distance_parameter_rows` is legitimately empty until a labelling
file is chosen, so the parametrized guard now has a short, documented
`DATA_DEPENDENT_PARAMETER_SOURCES` set — a source that resolves and returns
nothing yet is a data state, not a spec defect.

**Increment 20 (the three cleanups — PRD complete) — DONE.**

- **`pda2c/widgets.py` deleted (2,090 lines).** Nine of its ten classes were
  unreferenced once the PDA models became data-described. The tenth,
  `FretRdaAxisSettingsWidget`, was never a model widget at all — the FRET distance
  axis is one global setting — so it moved to
  `gui/widgets/fret_rda_axis_settings.py`. Its two distance spin boxes had a
  literal **tab** where the `Å` suffix should be, which is what the relocation
  screenshot showed.
- **`plot_classes` is gone (task 9).** `model_editor.py` resolves plots from
  `view_spec().plots` only; a model with none declared gets *no* plot tabs, which
  is a visible, fixable state — the old fallback could hand it another model's
  plots. `model_widget.py` went with it: `ModelWidget` existed to carry the
  metaclass that made a hand-written model widget *definable*, and there are none.
- **The equation validity badge and LaTeX preview are back**, as a `value` section
  of `kind: "expression"`. It renders the shared
  `gui/widgets/expression_input.py::ExpressionInput`, so every parse editor gets
  the safe-AST ✓/✗ badge, the reason in a tooltip, the typeset preview, the
  names-and-functions reference **and** parameter discovery — strictly more than
  `ParseFormulaWidget` had, from one implementation rather than two. First attempt
  hand-rolled an `ast.parse` check and a matplotlib preview inside `ValueWidget`;
  that was thrown away on finding `ExpressionInput`, because a second answer to
  "is this formula safe" is worse than none. `parse/widget.py` (1,022 lines) and
  `parseWidget.ui` are deleted; `parse/latex.py` stays — `equation_editor` uses it.

**One framework addition the equation field needed:** `_autoform_full_row`. Fields
pack two per row, and packed beside the model picker the equation editor shrank to
showing its last three characters. A field can now ask for the whole row.

**Two tests were red before this work and are fixed here.**
`test_model_widget_metaclass.py` named `chisurf.gui.widgets.models.tcspc.et` as its
worked example, and that module was deleted in increment 14 — so the file had been
failing since. It is replaced by `test_model_widget_modules_import.py`, which
asserts what still matters: every module under `gui/widgets/models` imports, and
each deprecated class path resolves to a **non-widget** model with the right
`name` (a path resolving to the wrong class is as broken as one that does not
resolve, and just as quiet).

*Not fixed here, and not caused here:* the PDA dynamic-fit convergence threshold
(`chi2r = 1.5339` against `< 1.5`), which reproduces identically on the commit
before this work. Recorded in [known issues](/references/known-issues.md) with the
measurement and the question to answer before moving the number.

# Where to pick this up: nothing open — how to keep it that way

PRD-38 is complete. What follows is for whoever adds or changes a model next.

**Adding a model.** Copy the shape from `core/models/pch/pch_model.py`: parameters
in lists with `label_text` on them, a `_species_parameter_rows` for a
`row_width: 2` table, zero-arg methods for any `button_row`, and a
`view_spec_file`. Add it to `JSON_DESCRIBED_TCSPC_MODELS` in
`test/gui/test_model_editor_integration.py` — that parametrized guard reads the
ERROR log `AutoForm` emits and carries on from, so it is what catches a **silently
dropped section**. Nothing else does.

**The pattern that made a model hard to extract**, and the thing to look for in
any Qt-side compute you meet: a computed output written through
`get_fitting_client()` from inside `update_model`, wrapped in a bare `except`. It
does nothing whenever that client is absent — headless, or before the editor has
registered the fit — and says nothing about it. FIDA's mean, PCH's component
defaults, dye-shape's D / tauD / cpm and ProteinMC's inter-dye distances were all
this. The fix is a direct parameter write; the parameter's own controller binding
repaints it.

**Deleting a registered class needs a deprecation alias.** A user copy of
`experiment_configs.yaml` *replaces* the bundled model list and a pickled project
pins class paths, so a path that stops resolving drops its entry from the model
menu without saying so. `test/gui/test_model_widget_modules_import.py` asserts each
old path still resolves to a non-widget model with the right `name`.

**How to verify a GUI change here:** the before/after parity rule
([testing workflow](/workflows/testing.md)) with `test/gui/migration_parity.py`.
Capture the legacy baseline *before* touching the code — it is unrecoverable
afterwards. Three traps in reading the result:

* a parity diff's "lost" list is mostly **renames** — `w0`→`w0[nm]`,
  `r[MHz]`→`rep`, `Linearize`→`DNL`, `...`→`…` — and names that moved into table
  cells also read as losses. Check each one before believing it;
* `capture()` renders the widget it is given at a fixed width, so put the editor
  in **no** parent layout first — a holder `QWidget` constrains it and the image
  comes back at the wrong size with its tables cropped, which looks exactly like
  a layout defect in the port;
* it expands folds through `CollapsibleBox.set_expanded`. Before increment 19 it
  clicked checkable `QToolButton`s, which AutoForm's headers are not, so every
  `collapsed` panel was silently missing from every pair taken with it.

# The `.ui` files under `models/` — all six are gone

| `.ui` | what replaced it |
|---|---|
| ~~`tcspc/tcspc_convolve.ui`~~ | deleted with the hand-written TCSPC widget layer (increment 14) |
| ~~`tcspc/tcspcCorrections.ui`~~ | the same |
| ~~`tcspc/et_model_free.ui`~~ | deleted; the ET model-free fit is deregistered — it was abstract and never openable, see [known issues](/references/known-issues.md) |
| ~~`parameter_transform/parameter_transform.ui`~~ | `parameter_transform.view.json`; its Python-`code:` catalogue turned out to be two class attributes on the shared catalogue mixin |
| ~~`stopped_flow/reaction.ui`~~ | `ReactionModel` + `reaction.view.json` (increment 18) |
| ~~`parse/parseWidget.ui`~~ | a `value` `kind: "expression"` over the shared `ExpressionInput` (increment 20) |

**The hand-written TCSPC widget layer is gone (increment 14).**
`LifetimeModelWidgetBase`, `LifetimeWidget`, `ConvolveWidget`, `CorrectionsWidget`,
`GenericWidget`, `AnisotropyWidget`, `GaussianWidget` and `DiscreteDistanceWidget`
were reachable only from each other once every model became data-described.
`chisurf/gui/widgets/models/tcspc/` now holds **only** `__init__.py` (deprecation
aliases) plus the κ² / Förster helpers the `kappa2_controls` section calls.

Two consequences that were handled in the same change, and one to know:

- `test/tcspc/test_convolve_widget_contract.py` was deleted (every test in it
  AST-inspected a deleted widget for button handlers). The durable half — the
  macro and action contracts in `test_tcspc_mcp_contracts.py` — is kept.
- `test_fit_tcspc.py` appended a Gaussian onto a model that now seeds one, giving
  two components. That is the **third** caller found doing this; define the
  ensemble (`gaussians.clear()` first) rather than appending onto whatever the
  constructor left.
- **The r(t) diagnostics panel went with `anisotropy.py` and has since been
  ported** (increment 15). Deleting it first was a mistake: it was the one
  un-ported control of every FRET/Lifetime editor and its only implementation.

# The reaction editor, as built (increment 18)

Kept as the record of what the `.ui` offered and where each control went, because
the widget it describes is deleted and this is the only place the mapping exists.
`ReactionWidget` was **abstract** — no `update_model` — so like the old
stopped-flow parse model it could never be opened, and functional compatibility
was the bar rather than file compatibility:

| what the old widget offered | how to declare it |
|---|---|
| per-species initial concentration + brightness | `parameter_group_table`, `row_width: 2` — **not** `state_table`, which binds plain float lists; these are fitting parameters and must carry Fixed/bounds columns |
| the reaction list (`A + B -> C`, with a rate) | `table` over `reaction_rows` with `selected_attr`, plus `button_row` over the zero-arg `add_reaction_row` / `remove_selected_reaction` / `clear_reactions` |
| reactions pasted as JSON | `value` `kind: "text"` writing a `reaction_json` property that parses and rebuilds |
| scaling / background / timeshift | `parameter_group_table` |
| x-range and autoscale | `toggle` only — the x-range is the fit window's own control and is deliberately not duplicated in the model panel |

`reaction_label(i)` writes a step with the species *names* rather than
`ReactionSystem.reaction_string`'s indices — `1.0 * [0] -> 1.0 * [1]` is
unreadable in a table the user is meant to check, and recognising the step is the
whole point of naming a species.

# Relationships
- Complements PRD-23 (thin view-only widgets) and PRD-26 (declarative generation from data).
- Generalized by [PRD-40](prd-40.md), which lifts this machinery out from under `models/` into a reusable `core/dataspec` + `gui/autoform` framework.
- Provides the numeric-input consumer that [PRD-42](prd-42.md) supplies a dependency-free replacement for.
- Realizes the [GUI & AutoForm](/subsystems/gui-autoform.md) direction over the [Core target](/specs/core.md).
