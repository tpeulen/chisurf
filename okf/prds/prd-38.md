---
type: PRD
prd: "38"
title: "PRD-38: Model/UI Split — view-spec JSON drives auto-generated model editors"
description: Splits a fitting model's compute definition from its editor by describing the editor in a co-located JSON view spec that a generic GUI renderer turns into the control panel.
status: in-progress
phase: "unassigned"
resource: chisurf/core/models/
tags: [prd, gui]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
PRD-38 makes a fitting model's editor the automatic result of its computational definition instead of a hand-written per-model widget that duplicates the model's structure and welds Qt to the compute side. Each model stays in one place (parameters plus `update_model` in `chisurf/core/models`, Qt-free), its editor is described in a hand-editable `<model>.view.json` file, and the GUI renders that spec by composition via `AutoModelWidget`. A strict, AST-CI-enforced boundary keeps `core/models/**` from importing any GUI toolkit, while a string-keyed registry provides an escape hatch for bespoke custom sections. The view-spec vocabulary has grown to parameter groups, dynamic groups, curve inputs, choices, toggles, and custom sections plus plots.

# Status
In-progress (unassigned phase). Data spine, boundary test, generic renderer, live wiring, section vocabulary, and the **TCSPC Lifetime + mixer flip** are done. The per-model backlog is the STATUS TABLE below; the TCSPC FRET family, the compute-in-GUI extractions, and dropping `plot_classes` remain.

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
| tcspc | `EtModelFree` (`gui/.../et.py:250`) | ❌ | B | extraction; then reuse `lcurve` |
| fcs | `MdfFCSModel`, `GeneralFCSModel`, `FCSKineticsModel` | ✅ | — | — |
| fcs | `ParseFCSModel` (`parse.view.json`) | ✅ | — | as above |
| fcs | `DyeShapeFCSModel` (`dye_volume_widget.py:68`) | ❌ | B | extraction |
| fcs | `MaxEntFCSModel` (`maxent_widget.py:24`), `MaxEntRHModel` (`:934`) | ❌ | B | extraction; GUI plot class `MaxEntFCSLCurvePlot` re-declarable as `lcurve` |
| pda2c/pda3c | all 7 | ✅ | — | — |
| deer | all 4 | ✅ | — | — |
| ics | both | ✅ | — | — |
| mfd | `Mfd2DModel` | ✅ | — | — |
| pch | `PchMultiComponentModel` (`pch/widgets.py:173`), `FidaModel` (`fida_widget.py:27`) | ❌ | B | extraction — `core/models/pch/fida.py` holds functions only |
| pcf | `ParsePCFModel` (`parse.view.json`) | ✅ | — | as above |
| stopped_flow | `ParseStoppedFlowModel` (`parse.view.json`) | ✅ | — | it had **no catalogue and could not be constructed** at all; both fixed |
| stopped_flow | `ReactionWidget` | ❌ | C | a reaction-scheme (species + rates) section |
| structure | `ProteinMCModelWidget` (1984 LOC) | ❌ | B+C | no core `Model` subclass; also needs a per-row-settings table and a worker run/stop control |
| global | `GlobalFitModel` (`globalfit.view.json`) | ✅ | — | — |
| global | `ParameterTransformModel` | ❌ | A | `parameter_transform.ui` |

**Tier D — dead code.** `gui/widgets/models/pda2c/widgets.py`: 9 of 10 classes are
unreferenced outside the file (~1,590 of 2,090 LOC), but `FretRdaAxisSettingsWidget`
(`:1047`) is live — `gui/main.py:1514` imports it. Relocate that one class, then
delete the rest; the file is **not** a wholesale delete, contrary to an earlier
reading of it. `gui/widgets/models/tcspc/lifetime_mix.py::LifetimeMixModelWidget`
is unregistered. The 5 stray `.ui` files that sat inside the Qt-free
`core/models/**` are deleted.

Counts at time of writing: 37 model classes ported across 10 families; **7 legacy
registrations remain** (FCS ×3, PCH ×2, ProteinMC, ReactionWidget) and **2 `.ui`
files under `models/`** (see the table below). `gui/widgets/models/tcspc/` is down
from ~5k LOC to an alias module plus two helper files. **The only hand-written TCSPC model left is
`EtModelFreeWidget`** — which is registered and *abstract*, so it cannot be
opened at all (see known-issues).

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
8. Migrate remaining structured models to `view.json`; delete their hand-written widgets. FCS (3), PDA (7), DEER (4), ICS (2), MFD (1) and TCSPC Lifetime + mixer are done; see the STATUS TABLE for what is left and what blocks each.
9. Remove `plot_classes` from models once all consumers read `view_spec().plots`.
10. Codify the table-rendering default and the before/after migration rule. — DONE

# Definition of Done

- A registered model class instantiated by `Fit` carries no Qt; the editor is a separate `AutoModelWidget`. Project save/load and fitting are unaffected.
- Editing `lifetime.view.json` (reorder sections, retitle, add/remove a plot) changes the live editor with no Python change.
- Custom UI (amplitude options, link/read, r(t)) works, referenced by key.
- Boundary test green; per-model widget files for migrated models deleted.

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

**START NEXT — the parse family, and what it needs (analysed, not yet built).**
This is the highest-value item left: one new section **retires four registered
models at once** (`ParseDecayModelWidget`, `ParseFCSWidget`, `ParsePCFWidget`,
`ParseStoppedFlowWidget`). The blocker is *not* the section — it is that **core
`ParseModel` knows nothing about the model catalogue**. Everything about it lives
in `gui/widgets/models/parse/widget.py`:

- `yaml.safe_load` of the catalogue and the path to it (`:114`, `:279`), plus a
  "load another YAML" file dialog (`:291`);
- `models` setter that repopulates the combobox (`:309-311`), `model_name`
  get/set by combobox index (`:316-322`);
- `set_initial_values` applying the YAML `initial:` block to the parameters
  (`:336-346`);
- the description + equation HTML shown to the user (`:181-182`, `:369`).

Core has only `func` (whose setter parses), `_models`, `_keys`, `_count` — the
dict is initialised empty and nothing fills it. So the port is **two steps**:

1. **Move the catalogue into core** (Qt-free): a `catalogue_file` /
   `load_catalogue(path)`, `catalogue_names` for a `choice`'s `options_source`, a
   `model_name` property whose setter sets `func` *and* applies the `initial:`
   values, and a `description` property. The catalogues are already data
   (`core/models/parse/models.yaml`, `core/models/tcspc/parse/tcspc_model.yaml`,
   `core/models/pcf/models.yaml`), so this is relocation, not design.
2. **Then one new `equation_catalogue` section**: catalogue combobox + the single
   equation field + rendered preview + description. *Do not* try to reuse
   `equation_editor` — it is a **table** of `output = expression` rows, a
   different shape from ParseModel's one `func` string, and forcing it would be
   worse than a new section. The LaTeX conversion
   (`gui/widgets/models/parse/latex.py`) is presentation and stays GUI-side.

With step 1 done, most of the editor is existing vocabulary (`choice` with
`options_source`, `info` for the description, `parameter_group_table` for the
parsed parameters) and the new section only owns the equation + preview.

(2) `EtModelFreeWidget` is tier B — its compute (`EtModelFree`) lives *inside*
`gui/widgets/models/tcspc/et.py`, so it needs extracting into `core/models/**`
first, after which its L-curve UI is a re-authoring job against the existing
`lcurve` section (increment 11 proved that pattern). Once both are gone,
`gui/widgets/models/tcspc/lifetime.py` can lose
`LifetimeWidget`/`LifetimeModelWidgetBase` and be deleted, and `gaussian.py`'s
`GaussianWidget` + `discrete_distance.py` go with it — they are now referenced
only by `tcspc/__init__.py` and one test. Generate each spec from
`fret_gaussian.view.json`, and check the group's parameters carry `label_text`
before trusting the table. (2) The
**global-fit migration** — `global_parameter_table` is built, tested and used by
*nothing* while `global_model/widget.py` + `globalfit.ui` hand-roll a weaker
version; cheapest real migration left. (3) The anisotropy r(t)
section, which closes Lifetime completely. (4) Relocate
`FretRdaAxisSettingsWidget` out of `pda2c/widgets.py`, then delete the ~1,590
dead lines around it. (5) Task 9 — drop `plot_classes`.

**How to verify any of it:** the before/after parity rule
([testing workflow](/workflows/testing.md)) with `test/gui/migration_parity.py`.
Capture the legacy baseline *before* touching the code — it is unrecoverable
afterwards. Do not trust a parity diff's "lost" list at face value: renames
(`r[MHz]`→`rep`, `Linearize`→`DNL`, `...`→`…`) and names that moved into table
cells both read as losses.


# The `.ui` files under `models/` — what each one is waiting on

Six remain. Two are already dead; the other four each block on one named thing, so
"port the `.ui` files" is really four separate pieces of work:

| `.ui` | loaded by | registered? | blocked on |
|---|---|:--:|---|
| ~~`tcspc/tcspc_convolve.ui`~~ | — | — | **deleted** with the hand-written widget layer |
| ~~`tcspc/tcspcCorrections.ui`~~ | — | — | **deleted** |
| ~~`tcspc/et_model_free.ui`~~ | — | — | **deleted**; the ET model-free fit is deprecated, see [known issues](/references/known-issues.md) |
| ~~`parameter_transform/parameter_transform.ui`~~ | — | — | **deleted**; its catalogue holds Python `code:`, which is two class attributes on the shared catalogue mixin |
| `parse/parseWidget.ui` | `parse/widget.py::ParseFormulaWidget` | no | a `value` `kind: "expression"` (validity badge + LaTeX preview). Kept *only* for those two controls |
| `stopped_flow/reaction.ui` | `stopped_flow.py::ReactionWidget` | yes | a core reaction model + list-backed sections — designed below |

**The hand-written TCSPC widget layer is gone (increment 14).**
`LifetimeModelWidgetBase`, `LifetimeWidget`, `ConvolveWidget`, `CorrectionsWidget`,
`GenericWidget`, `AnisotropyWidget`, `GaussianWidget` and `DiscreteDistanceWidget`
were reachable only from each other once every TCSPC model became data-described.
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

# Designing the reaction editor (the last `.ui`)

`ReactionWidget` is **abstract** — no `update_model` — so like `EtModelFreeWidget`
and the old stopped-flow parse model it could never be opened. Functional
compatibility is the bar, not file compatibility, so the surface to reproduce is:

| what the old widget offered | how to declare it |
|---|---|
| per-species initial concentration + brightness | `state_table` (rows are species, columns are the two lists), with `size_attr` tracking `n_species` |
| the reaction list (`A + B -> C`, with a rate) | `table` over a `reaction_strings` source, plus `button_row` add / remove / clear over `add_reaction` / `pop` / `clear` |
| reactions pasted as JSON | `value` `kind: "text"` writing a `reaction_json` property that parses and rebuilds |
| scaling / background / timeshift | `parameter_group_table` |
| x-range and autoscale | `value` ×2 + `toggle` |

What core needs first: a `ReactionModel(ReactionSystem, Model)` in
`core/models/stopped_flow/` that **implements `update_model`** (integrate the rate
equations onto the fit's time axis), exposes `reaction_strings` (core already has
`reaction_string(i)`), a settable `reaction_json`, and zero-arg
`add_reaction_row` / `remove_selected_reaction` over the selection state — the
same shape the global-fit editor uses, since `button_row` calls zero-arg model
methods.

# Relationships
- Complements PRD-23 (thin view-only widgets) and PRD-26 (declarative generation from data).
- Generalized by [PRD-40](prd-40.md), which lifts this machinery out from under `models/` into a reusable `core/dataspec` + `gui/autoform` framework.
- Provides the numeric-input consumer that [PRD-42](prd-42.md) supplies a dependency-free replacement for.
- Realizes the [GUI & AutoForm](/subsystems/gui-autoform.md) direction over the [Core target](/specs/core.md).
