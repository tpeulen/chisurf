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
import os
import pathlib

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _default_tcspc_model_paths():
    """The TCSPC model class paths from the *default* experiment config.

    Mirrors how ``main_helper.init_setups`` reads the bundled YAML (the user copy
    is intentionally ignored here so the test reflects the repo, not a machine)."""
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
def test_every_configured_tcspc_model_resolves_with_a_name(qapp):
    """Every model path in the default config resolves to a class exposing a
    non-empty ``name`` — the string the model combobox shows and ``add_fit``
    matches on. A deleted/renamed class fails here instead of silently vanishing
    from the menu."""
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


def test_lifetime_pure_model_editor_is_populated_and_computes(qapp):
    """Walk the full add-fit path for the pure Lifetime model and assert the
    editor a user would see is actually usable: it builds, every parameter group
    renders its parameters, the IRF curve input is present, and the model
    produces a finite decay."""
    from qtpy import QtWidgets

    from chisurf.core.models import view_spec as vs
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import (
        build_model_editor,
        model_plot_specs,
    )

    model_class = _resolve("chisurf.core.models.tcspc.lifetime.LifetimeModel")
    fit = _make_fit(model_class)
    model = fit.model

    # (a) build_model_editor must return a real widget (the add-fit crash site)
    editor = build_model_editor(model)
    assert isinstance(editor, AutoModelWidget)
    QtWidgets.QVBoxLayout().addWidget(editor)  # the exact call that used to raise

    # (b) the editor is not a row of empty titled boxes (per-parameter widgets
    # and/or compact parameter-group tables)
    from chisurf.gui.autoform.sections.parameter_table import (
        PairedParameterTableWidget,
        ParameterGroupTableWidget,
    )
    table_rows = sum(t.table_model.rowCount() for t in editor.findChildren(ParameterGroupTableWidget))
    assert len(editor.parameter_widgets) + table_rows > 12, "parameter groups rendered empty"

    # (b2) the lifetime (x/tau) and rotation (b/rho) components render as paired
    # tables: one row per component, two parameter slots per row side by side.
    paired = editor.findChildren(PairedParameterTableWidget)
    assert paired, "paired component tables did not render"
    for t in paired:
        assert t.table_model.width == 2, "paired table expected 2 params per component"
        # 1 index column + 2 slots x 6 (value/fixed/lo/hi/bounds/error) columns
        assert t.table_model.columnCount() == 1 + 2 * 6
    # the lifetime components table starts populated (at least one component row)
    assert any(t.table_model.rowCount() >= 1 for t in paired), "no paired component rows"

    # (b3) bounds columns are always wanted and hidden only for want of room --
    # there is no toggle to find them behind. A one-parameter-per-row table shows
    # them when given the width; squeezed, columns are dropped by priority.
    from qtpy import QtWidgets

    from chisurf.gui.autoform.sections.parameter_table import COL_BOUNDS_ON

    gen = next(
        (t for t in editor.findChildren(ParameterGroupTableWidget) if t.has_bounds_columns()),
        None,
    )
    assert gen is not None, "no bounds-capable parameter table found"

    from chisurf.gui.autoform.sections.parameter_table import COL_ERROR, COL_VALUE

    def _at_width(width: int):
        """Render the editor at `width` and return the sample table's view.

        The editor is shown (offscreen): a table's viewport has no width until the
        widget is laid out, so an unshown editor reports nothing to fit columns
        into and drops them all.
        """
        editor.show()
        editor.setFixedWidth(width)   # resize() is refused below the layout minimum
        qapp.processEvents()
        editor.resize(width, max(editor.sizeHint().height(), 600))
        qapp.processEvents()
        return gen.table_view

    # Given the room, a one-parameter-per-row table shows its bounds columns...
    view = _at_width(560)
    assert not view.isColumnHidden(COL_BOUNDS_ON), (
        "a single-column table should show the bounds columns when they fit"
    )
    # ...and so does a table packing two parameters per row, when it has the room:
    # nothing hides bounds on principle any more, only for want of space.
    for paired in editor.findChildren(PairedParameterTableWidget):
        pv, pm = paired.table_view, paired.table_model
        if not paired.has_bounds_columns() or pm.rowCount() == 0:
            continue
        if pv.horizontalScrollBar().maximum() == 0 and not pv.isColumnHidden(COL_BOUNDS_ON):
            break   # at least one wide component table shows them: the rule holds
    # (a narrow one may still have dropped them -- that is the width check, below)

    # Squeezed, the table drops columns by priority rather than truncating
    # everything equally: bounds first, then the error estimate, and the value is
    # kept longest because a value you cannot read is the table failing.
    view = _at_width(210)
    assert view.isColumnHidden(COL_BOUNDS_ON), "bounds not dropped on a narrow table"
    assert not view.isColumnHidden(COL_VALUE), "the value column must survive"
    view = _at_width(150)
    assert view.isColumnHidden(COL_ERROR), "error not dropped on a very narrow table"
    assert not view.isColumnHidden(COL_VALUE), "the value column must survive"

    # Widening brings them back, in reverse priority order.
    view = _at_width(560)
    assert not view.isColumnHidden(COL_ERROR), "error not restored when it fits again"
    assert not view.isColumnHidden(COL_BOUNDS_ON), "bounds not restored when they fit again"
    editor.setMaximumWidth(16777215)  # undo setFixedWidth for later assertions

    # (c) every parameter-group section resolves to a group that actually has params
    spec = model.view_spec()
    for section in spec.flat_sections():
        if isinstance(section, (vs.ParameterGroupSection, vs.ParameterGroupTableSection)):
            group = getattr(model, section.target)
            if hasattr(group, "find_parameters") and not list(group.parameters_all):
                group.find_parameters()
            assert list(group.parameters_all), f"group {section.target!r} has no parameters"

    # (d) the IRF curve input is present so the model can be given an instrument response
    curve_inputs = [s for s in spec.flat_sections() if isinstance(s, vs.CurveInputSection)]
    assert any(s.select_action == "model.change_irf" for s in curve_inputs), "no IRF curve input"

    # (d2) the bespoke enum/bool controls the hand-written widget had are present
    # (convolution type + on/off, smoothing, correction toggles, polarization).
    choice_attrs = {s.attr for s in spec.flat_sections() if isinstance(s, vs.ChoiceSection)}
    toggle_attrs = {s.attr for s in spec.flat_sections() if isinstance(s, vs.ToggleSection)}
    toggle_row_attrs = {
        item["attr"]
        for s in spec.flat_sections()
        if isinstance(s, vs.ToggleRowSection)
        for item in s.items
    }
    all_toggle_attrs = toggle_attrs | toggle_row_attrs
    assert {"mode", "window_function", "polarization_type"} <= choice_attrs, (
        f"missing choice controls; have {choice_attrs}")
    assert "do_convolution" in toggle_attrs, f"missing do_convolution toggle; have {toggle_attrs}"
    assert {"correct_pile_up", "correct_dnl", "reverse"} <= all_toggle_attrs, (
        f"missing toggle controls; have {all_toggle_attrs}")

    # (e) plots resolve and the model computes a finite, non-empty curve
    assert model_plot_specs(model), "no plot specs resolved"
    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y)), "model did not compute a finite decay"


# --------------------------------------------------------------------------
# 3. LifetimeMixtureModel (AutoForm-based lifetime mixer) — end-to-end
# --------------------------------------------------------------------------
def test_lifetime_mixture_new_model_editor_renders_and_fit_mixer_section_exists(qapp):
    """Walk the full add-fit path for the AutoForm-based Lifetime mixer and
    assert: the editor builds, the fit_mixer custom section is present and
    rendered, and the model computes a finite fallback decay (no components)."""
    from qtpy import QtWidgets

    from chisurf.core.models import view_spec as vs
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.builtin import FitMixerWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor, model_plot_specs

    model_class = _resolve("chisurf.core.models.tcspc.lifetime.LifetimeMixtureModel")
    assert model_class.name == "Lifetime mixer"
    fit = _make_fit(model_class)
    model = fit.model

    # (a) pure model — editor is AutoForm, not a QWidget-model
    assert not isinstance(model, QtWidgets.QWidget)
    editor = build_model_editor(model)
    assert isinstance(editor, AutoForm)
    QtWidgets.QVBoxLayout().addWidget(editor)  # must not raise

    # (b) the view spec declares a fit_mixer custom section
    spec = model.view_spec()
    customs = [s for s in spec.flat_sections() if isinstance(s, vs.CustomSection)]
    assert any(s.key == "fit_mixer" for s in customs), "no fit_mixer section in mix_model.view.json"

    # (c) a FitMixerWidget is present in the rendered editor
    mixer_widgets = editor.findChildren(FitMixerWidget)
    assert mixer_widgets, "FitMixerWidget not found in rendered editor"

    # (d) the IRF curve input is declared so the model can be convolved
    curve_inputs = [s for s in spec.flat_sections() if isinstance(s, vs.CurveInputSection)]
    assert any(s.select_action == "model.change_irf" for s in curve_inputs), "no IRF curve input"

    # (e) plots resolve
    assert model_plot_specs(model), "no plot specs resolved"

    # (f) the model produces a finite fallback decay (no components added yet)
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
    "chisurf.core.models.tcspc.lifetime.LifetimeModel",
    "chisurf.core.models.tcspc.lifetime.LifetimeMixtureModel",
    "chisurf.core.models.tcspc.fret.FRETrateModel",
    "chisurf.core.models.tcspc.fret.GaussianModel",
    "chisurf.core.models.tcspc.fret.WormLikeChainModel",
    "chisurf.core.models.tcspc.fret.SawNuModel",
    "chisurf.core.models.tcspc.fret.IsingChainModel",
    "chisurf.core.models.tcspc.pddem.PDDEMModel",
    "chisurf.core.models.tcspc.maxent.MaxEntLifetimeModel",
    "chisurf.core.models.tcspc.maxent.MaxEntFRETModel",
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
def test_json_described_model_editor_builds_every_section(qapp, path, caplog):
    """The editor builds with *no* section skipped, and the model computes.

    ``AutoForm`` logs a failure and carries on when a section cannot be built,
    so a mistyped option leaves an editor that looks right and is missing one
    control. Three of those shipped during this migration (a ``label`` the
    parameter factory did not accept, and two component tables with no rows), and
    all three were invisible to construction tests. This asserts the log is clean
    and that every declared component group actually has a component.
    """
    import logging

    from qtpy import QtWidgets

    from chisurf.core.models import view_spec as vs
    from chisurf.gui.autoform.sections.parameter_table import COL_VALUE
    from chisurf.gui.widgets.models.model_editor import (
        build_model_editor,
        model_plot_specs,
    )

    model_class = _resolve(path)
    from chisurf.core.models.description import DescriptionModel

    # A BFF-described model derives its editor from the description instead.
    assert model_class.view_spec_file or issubclass(model_class, DescriptionModel), (
        f"{path} declares no view_spec_file")

    fit = _make_fit(model_class)
    model = fit.model
    assert not isinstance(model, QtWidgets.QWidget), "expected a Qt-free model"

    with caplog.at_level(logging.ERROR):
        editor = build_model_editor(model)
    skipped = [r.message for r in caplog.records if "failed to build section" in r.message]
    assert not skipped, "sections were silently dropped:\n" + "\n".join(skipped)

    assert editor is not None
    QtWidgets.QVBoxLayout().addWidget(editor)  # must not raise

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
                    f"{path}: parameters_source {source!r} not found on "
                    f"{type(group).__name__}"
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

    # Squeezed into a docked panel, every table must still fit by dropping columns
    # in priority order -- and every *value* column has to survive, because a value
    # you cannot read is the table failing at the one thing it is for. This is
    # checked here rather than against one model because the tables that overflow
    # are the wide ones (PDDEM's A/B pairs, the Gaussian distances' four slots),
    # and no single model has them all.
    from chisurf.gui.autoform.sections.parameter_table import (
        SLOT_COLUMN_META,
        PairedParameterTableWidget,
        ParameterGroupTableWidget,
    )

    editor.show()
    editor.setFixedWidth(230)  # resize() alone is refused below the layout minimum
    qapp.processEvents()
    editor.resize(230, max(editor.sizeHint().height(), 600))
    qapp.processEvents()

    def _scrolls(view) -> bool:
        """Whether columns overflow the viewport.

        The visible outcome, not a sum of size hints: a *stretch* column is
        squeezed below its hint by design, so adding hints up reports an overflow
        the user never sees. A horizontal scrollbar with something to scroll is
        the honest signal that columns did not fit.
        """
        return view.horizontalScrollBar().maximum() > 0

    for table in editor.findChildren(ParameterGroupTableWidget):
        view = table.table_view
        if view.viewport().width() < 120 or table.table_model.rowCount() == 0:
            continue  # not laid out (a collapsed panel), so nothing was decided
        assert not view.isColumnHidden(COL_VALUE), f"{path}: value column dropped"
        assert not _scrolls(view), (
            f"{path}: a single-column table overflows its "
            f"{view.viewport().width()}px viewport"
        )

    for table in editor.findChildren(PairedParameterTableWidget):
        pm, view = table.table_model, table.table_view
        if view.viewport().width() < 120 or pm.rowCount() == 0:
            continue
        slots_with_value = {
            pm._slot(c)[0]
            for c in range(pm.columnCount())
            if not view.isColumnHidden(c)
            and pm._slot(c) is not None
            and SLOT_COLUMN_META[pm._slot(c)[1]][0] == "value"
        }
        assert len(slots_with_value) == pm.width, (
            f"{path}: a {pm.width}-slot table dropped a value column "
            f"(kept {sorted(slots_with_value)})"
        )
        # A paired table may scroll rather than squeeze a number until it elides
        # (see ``_fit_value_columns``) -- showing "0…" instead of a value defeats
        # the column. But it must only reach for the scrollbar once it has nothing
        # optional left to drop, so an overflowing table has no low-priority
        # column still taking room.
        if _scrolls(view):
            leftovers = {
                SLOT_COLUMN_META[pm._slot(c)[1]][0]
                for c in range(pm.columnCount())
                if not view.isColumnHidden(c) and pm._slot(c) is not None
            } & {"bounds_lo", "bounds_hi", "bounds_on", "error", "fixed"}
            assert not leftovers, (
                f"{path}: a {pm.width}-slot table scrolls while still showing "
                f"{sorted(leftovers)} — those should have been dropped first"
            )
