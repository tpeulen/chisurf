"""End-to-end *integration* smoke test for the model → editor → compute path.

This is the safety net that catches the class of regressions a unit test on an
isolated helper misses — the ones that only appear when you walk the **whole**
path a user walks when adding a fit (PRD-38). Each assertion here maps to a real
bug that reached the running GUI during the Lifetime model/UI split:

* model-name resolution from the experiment config  → "Lifetime" vanished from
  the model combobox after a class was deleted/renamed.
* ``build_model_editor(fit.model)`` returns a widget → ``addWidget(fit.model)``
  crashed because the live add-fit path never went through the seam.
* every parameter-group section renders its parameters → convolve/generic/
  corrections drew empty because their params surface only via
  ``find_parameters()``.
* curve inputs (IRF) are present and the model computes → the flipped model
  could not be given an instrument response, so it "did not compute".

Run headless in the arm64 env, in its own process:

    QT_QPA_PLATFORM=offscreen python -m pytest \
        test/gui/test_model_editor_integration.py -p no:cov -o addopts=""

If you change a model, its ``view.json``, the renderer, or the add-fit wiring,
this file is the first thing to run.
"""

from __future__ import annotations

import importlib
import pathlib

import numpy as np
import pytest

def _default_tcspc_model_paths():
    """The TCSPC model class paths from the *default* experiment config.

    Mirrors how ``main_helper.init_setups`` reads the bundled YAML (the user copy
    is intentionally ignored here so the test reflects the repo, not a machine).
    """
    import yaml

    import chisurf.core.settings as settings

    cfg = pathlib.Path(settings.__file__).parent / "experiment_configs.yaml"
    data = yaml.safe_load(cfg.read_text())
    return list(data.get("tcspc", {}).get("models", []))


def _resolve(path):
    """Resolve a dotted class path exactly like ``main_helper._resolve_class``."""
    module_name, class_name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module_name), class_name)


# --------------------------------------------------------------------------
# 1. Config resolution — would have caught the missing "Lifetime" combobox entry
# --------------------------------------------------------------------------
def test_every_configured_tcspc_model_resolves_with_a_name():
    """Every model path in the default config resolves to a class exposing a
    non-empty ``name`` — the string the model combobox shows and ``add_fit``
    matches on. A deleted/renamed class fails here instead of silently vanishing
    from the menu.
    """
    paths = _default_tcspc_model_paths()
    assert paths, "no TCSPC models configured"
    problems = []
    names = []
    for path in paths:
        try:
            cls = _resolve(path)
        except Exception as exc:
            problems.append(f"{path}: unresolved ({exc})")
            continue
        name = getattr(cls, "name", None)
        if not name or not str(name).strip():
            problems.append(f"{path}: missing/empty .name")
        else:
            names.append(str(name))
    assert not problems, "configured models that won't appear in the menu:\n" + "\n".join(problems)
    # the canonical Lifetime entry must be present and resolvable
    assert any(n.strip() == "Lifetime" for n in names), f"'Lifetime' missing from {names}"


# --------------------------------------------------------------------------
# 2. Pure-model editor is populated and the model computes — the heart of it
# --------------------------------------------------------------------------
def _make_fit(model_class):
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve

    # Strictly positive: these are time / lag axes, and an equation containing
    # log(x) or 1/x is legitimately non-finite at zero -- a fixture starting at 0
    # made a correct model look broken.
    x = np.linspace(0.05, 25, 256)
    data = DataCurve(x=x, y=np.exp(-x / 4.0) + 1.0)
    return fit_mod.Fit(model_class=model_class, data=data)


def test_lifetime_pure_model_spec_is_complete_and_computes():
    """Walk the add-fit path for the Lifetime model (a view on BFF's tcspc_lifetime) and assert
    the spec an editor is generated from is usable: the IRF input and the switches are declared,
    the plots resolve, and the model computes.
    """
    from chisurf.core.models import view_spec as vs
    from chisurf.emtk.fit_pages.plots import model_plot_specs

    model_class = _resolve("chisurf.core.models.description.tcspc_lifetime")
    fit = _make_fit(model_class)
    model = fit.model
    assert model.problem is not None, model.missing

    spec = model.view_spec()
    curve_inputs = [s for s in spec.flat_sections() if isinstance(s, vs.CurveInputSection)]
    assert any(s.select_action == "model.change_irf" for s in curve_inputs), "no IRF curve input"

    toggles = {s.attr for s in spec.flat_sections() if isinstance(s, vs.ToggleSection)}
    toggles |= {
        f"{item['target']}.{item['attr']}"
        for s in spec.flat_sections()
        if isinstance(s, vs.ToggleRowSection)
        for item in s.items
    }
    assert {"do_convolution", "corrections.correct_pile_up", "corrections.reverse"} <= toggles, (
        toggles
    )
    model.corrections.reverse = True
    assert model.get_scalar("reverse_linearization") == 1.0

    assert model_plot_specs(model), "no plot specs resolved"
    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y)), "model did not compute a finite decay"


# --------------------------------------------------------------------------
# 3. LifetimeMixtureModel (AutoForm-based lifetime mixer) — end-to-end
# --------------------------------------------------------------------------
def test_lifetime_mixture_spec_declares_the_fit_mixer():
    """The Lifetime mixer declares its fit_mixer section and IRF input, its plots resolve, and
    the model computes a finite fallback decay (no components).
    """
    from chisurf.core.models import view_spec as vs
    from chisurf.emtk.fit_pages.plots import model_plot_specs

    model_class = _resolve("chisurf.core.models.description.tcspc_mixture")
    assert model_class.name == "Lifetime mixture"
    fit = _make_fit(model_class)
    model = fit.model

    spec = model.view_spec()
    customs = [s for s in spec.flat_sections() if isinstance(s, vs.CustomSection)]
    assert any(s.key == "fit_mixer" for s in customs), "no fit_mixer section in the mixture editor"

    curve_inputs = [s for s in spec.flat_sections() if isinstance(s, vs.CurveInputSection)]
    assert any(s.select_action == "model.change_irf" for s in curve_inputs), "no IRF curve input"

    assert model_plot_specs(model), "no plot specs resolved"

    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y)), "model did not compute a finite fallback decay"


# --------------------------------------------------------------------------
# 4. Every JSON-described TCSPC model builds a populated editor and computes
# --------------------------------------------------------------------------
#: The TCSPC models whose editors are generated from a co-located view spec.
#: Extend this when a model is migrated -- it is the cheapest guard against the
#: whole class of defects the migration kept producing: a section silently
#: dropped because its factory rejected an option, and a component table that
#: renders with no rows because nothing seeded a component.
JSON_DESCRIBED_TCSPC_MODELS = [
    "chisurf.core.models.description.tcspc_lifetime",
    "chisurf.core.models.description.tcspc_mixture",
    "chisurf.core.models.description.tcspc_fret_discrete",
    "chisurf.core.models.description.tcspc_fret_gaussian",
    "chisurf.core.models.description.tcspc_fret_worm_like_chain",
    "chisurf.core.models.description.tcspc_fret_saw_nu",
    "chisurf.core.models.description.tcspc_fret_ising_chain",
    "chisurf.core.models.description.tcspc_pddem",
    "chisurf.core.models.description.tcspc_maxent_lifetime",
    "chisurf.core.models.description.tcspc_maxent_fret",
    "chisurf.core.models.tcspc.fret_structure.FRETStructure",
    "chisurf.core.models.tcspc.parse.tcspc_parse.ParseDecayModel",
    "chisurf.core.models.fcs.parse.ParseFCSModel",
    "chisurf.core.models.fcs.dye_shape.DyeShapeFCSModel",
    "chisurf.core.models.fcs.maxent_models.MaxEntFCSModel",
    "chisurf.core.models.fcs.maxent_models.MaxEntRHModel",
    "chisurf.core.models.pcf.parse.ParsePCFModel",
    "chisurf.core.models.stopped_flow.parse.ParseStoppedFlowModel",
    "chisurf.core.models.stopped_flow.reaction.ReactionModel",
    "chisurf.core.models.structure.proteinmc_model.ProteinMCModel",
    "chisurf.core.models.global_model.globalfit.GlobalFitModel",
    "chisurf.core.models.parameter_transform.model.ParameterTransformModel",
    "chisurf.core.models.pch.fida_model.FidaModel",
    "chisurf.core.models.pch.pch_model.PchMultiComponentModel",
]


#: ``parameters_source`` names whose list is legitimately empty until the user
#: supplies a file. The guard exists to catch a *mistyped* source and an unseeded
#: component group; a source that resolves and returns nothing yet is a data
#: state, not a spec defect. Keep this list short and say why for each entry.
DATA_DEPENDENT_PARAMETER_SOURCES = {
    # ProteinMC's inter-fluorophore distances come from the labelling file, and
    # a fresh model has none.
    "_distance_parameter_rows",
}


@pytest.mark.parametrize("path", JSON_DESCRIBED_TCSPC_MODELS)
def test_json_described_model_editor_builds_every_section(path):
    """Every section of the spec resolves, and the model computes.

    ``AutoForm`` logs a failure and carries on when a section cannot be built,
    so a mistyped option leaves an editor that looks right and is missing one
    control. Three of those shipped during this migration (a ``label`` the
    parameter factory did not accept, and two component tables with no rows), and
    all three were invisible to construction tests. This asserts the log is clean
    and that every declared component group actually has a component.
    """
    from chisurf.core.models import view_spec as vs
    from chisurf.core.models.description import DescriptionModel
    from chisurf.emtk.fit_pages.plots import model_plot_specs

    model_class = _resolve(path)

    # A BFF-described model derives its editor from the description instead.
    assert model_class.view_spec_file or issubclass(model_class, DescriptionModel), (
        f"{path} declares no view_spec_file"
    )

    fit = _make_fit(model_class)
    model = fit.model

    spec = model.view_spec()

    # every parameter-group target resolves to something with parameters to show.
    # An omitted target means the model itself (the renderer's convention), and a
    # `parameters_source` names the parameters explicitly instead of taking
    # `parameters_all` -- which is what a model carrying its own parameters needs,
    # since `parameters_all` there is every nuisance group too.
    for section in spec.flat_sections():
        if isinstance(section, (vs.ParameterGroupSection, vs.ParameterGroupTableSection)):
            group = model if not section.target else getattr(model, section.target, None)
            assert group is not None, f"{path}: no group {section.target!r}"
            source = getattr(section, "parameters_source", None)
            if source:
                # A method *or* a plain attribute: a parameter list is a natural
                # thing to hold as a list, and the renderer accepts either.
                value = getattr(group, source, None)
                assert value is not None or hasattr(group, source), (
                    f"{path}: parameters_source {source!r} not found on {type(group).__name__}"
                )
                resolved = list(value() if callable(value) else value)
                if source not in DATA_DEPENDENT_PARAMETER_SOURCES:
                    assert resolved, f"{path}: parameters_source {source!r} is empty"
                continue
            if hasattr(group, "find_parameters") and not list(group.parameters_all):
                group.find_parameters()
            assert list(group.parameters_all), f"{path}: group {section.target!r} is empty"

    # every dynamic (component) group starts with at least one component, or its
    # table renders as bare "Value / Fixed / Error" columns with no rows
    for section in spec.flat_sections():
        if isinstance(section, vs.DynamicGroupSection) and section.min_rows:
            group = getattr(model, section.target, None)
            assert group is not None, f"{path}: no group {section.target!r}"
            assert len(group) >= section.min_rows, (
                f"{path}: {section.target!r} has {len(group)} components, "
                f"min_rows={section.min_rows} — the editor table will be empty"
            )

    assert model_plot_specs(model), f"{path}: no plot specs resolved"
    model.update()
    if not hasattr(model, "y"):
        # Not every fitting model is a *curve*: a parameter transform maps
        # parameters to parameters and has no y at all. It still has to build an
        # editor and update without raising, which is what was checked above.
        return
    y = np.asarray(model.y)
    assert np.all(np.isfinite(y)), f"{path}: computed a non-finite curve"
    # A *container* model (a global fit) has nothing of its own to compute until
    # member fits are added, so an empty curve is correct there and only there.
    if y.size == 0:
        assert not list(getattr(model, "fits", []) or []), (
            f"{path}: has member fits but computed nothing"
        )
    else:
        assert y.size > 0
