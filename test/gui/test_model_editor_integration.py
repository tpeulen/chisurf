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

    x = np.linspace(0, 25, 256)
    data = DataCurve(x=x, y=np.exp(-x / 4.0) + 1.0)
    return fit_mod.Fit(model_class=model_class, data=data)


def test_lifetime_pure_model_editor_is_populated_and_computes(qapp):
    """Walk the full add-fit path for the pure Lifetime model and assert the
    editor a user would see is actually usable: it builds, every parameter group
    renders its parameters, the IRF curve input is present, and the model
    produces a finite decay."""
    from qtpy import QtWidgets
    from chisurf.core.models import view_spec as vs
    from chisurf.gui.widgets.models.model_editor import (
        build_model_editor,
        model_plot_specs,
    )
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

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

    # (b3) each bounds_toggle panel puts a "bounds" toggle in its header; the
    # Lo/Hi/Bounds columns start hidden (to save width) and the toggle reveals them.
    from qtpy import QtWidgets
    from chisurf.gui.autoform.sections.parameter_table import COL_BOUNDS_ON

    toggles = [b for b in editor.findChildren(QtWidgets.QToolButton) if b.text() == "bounds"]
    assert toggles, "no 'bounds' toggle rendered in panel headers"
    gen = next(
        (t for t in editor.findChildren(ParameterGroupTableWidget) if t.has_bounds_columns()),
        None,
    )
    assert gen is not None, "no bounds-capable parameter table found"
    assert gen.table_view.isColumnHidden(COL_BOUNDS_ON), "bounds column not hidden by default"
    gen.set_bounds_visible(True)
    assert not gen.table_view.isColumnHidden(COL_BOUNDS_ON), "bounds column not shown after toggle"
    gen.set_bounds_visible(False)
    assert gen.table_view.isColumnHidden(COL_BOUNDS_ON), "bounds column not re-hidden"

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
# 3. LifetimeMixtureNewModel (AutoForm-based lifetime mixer) — end-to-end
# --------------------------------------------------------------------------
def test_lifetime_mixture_new_model_editor_renders_and_fit_mixer_section_exists(qapp):
    """Walk the full add-fit path for the AutoForm-based Lifetime mixer and
    assert: the editor builds, the fit_mixer custom section is present and
    rendered, and the model computes a finite fallback decay (no components)."""
    from qtpy import QtWidgets
    from chisurf.core.models import view_spec as vs
    from chisurf.gui.widgets.models.model_editor import build_model_editor, model_plot_specs
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.builtin import FitMixerWidget

    model_class = _resolve("chisurf.core.models.tcspc.lifetime.LifetimeMixtureNewModel")
    assert model_class.name == "Lifetime mixer (new)"
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
