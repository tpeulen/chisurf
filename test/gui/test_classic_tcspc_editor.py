"""The classic TCSPC editors work on the BFF views, control by control.

The Lifetime and FRET editors are the classic ``view.json`` files; their rows,
switches and buttons address the groups of
:mod:`chisurf.core.models.tcspc.classic_editor`. Each test here drives the
widget a user drives and asserts what changed in the BFF model underneath.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("qtpy")
pytest.importorskip("IMP.bff")

import chisurf as cs
import chisurf.core.fitting.fit as fit_mod
from chisurf.core.data import DataCurve
from chisurf.core.fluorescence.tcspc.irf import synthetic_irf
from chisurf.core.models.description import for_family


def _fit(family: str):
    x = np.arange(512) * 0.05
    irf = synthetic_irf(x, center_ns=2.0, fwhm_ns=0.2, norm=True) * 1e4
    y = 1e4 * np.exp(-x / 3.0) + 10.0
    fit = fit_mod.FitGroup(
        data=cs.core.data.DataCurveGroup([DataCurve(x=x, y=y, ey=np.sqrt(y), name="decay")]),
        model_class=for_family(family),
    )
    model = fit.grouped_fits[0].model
    model.set_dataset("response", DataCurve(x=x, y=irf, name="irf"))
    model.problem
    return fit, model


@pytest.fixture
def lifetime(qapp):
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit, model = _fit("tcspc_polarized")
    cs.fits.append(fit)
    editor = build_model_editor(model)
    editor.show()
    qapp.processEvents()
    yield fit, model, editor
    cs.fits.remove(fit)
    editor.close()


def _panels(editor) -> list:
    from chisurf.gui.widgets.collapsible_box import CollapsibleBox

    return [box.title() for box in editor.findChildren(CollapsibleBox)]


def _row(editor, name: str):
    """(table widget, row index) of the parameter called *name*."""
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget

    for table in editor.findChildren(ParameterGroupTableWidget):
        for row, parameter in enumerate(table.table_model._params):
            if parameter.name == name:
                return table, row
    raise AssertionError(f"no row {name!r}")


def _toggle(editor, attr: str):
    """The checkbox of the toggle section bound to *attr*."""
    from chisurf.gui.autoform.sections.builtin import ToggleWidget

    return next(t for t in editor.findChildren(ToggleWidget) if t._section.attr == attr).checkbox


def _edit(editor, name: str, value: float) -> None:
    from chisurf.gui.autoform.sections.parameter_table import COL_VALUE

    table, row = _row(editor, name)
    index = table.table_model.index(row, COL_VALUE)
    assert table.table_model.setData(index, value)


def test_the_lifetime_editor_has_the_classic_panels(lifetime):
    _fit_, model, editor = lifetime
    assert model.name == "Lifetime"
    assert _panels(editor)[:5] == [
        "Convolution",
        "Generic",
        "Corrections",
        "Lifetimes",
        "Anisotropy",
    ]
    labels = [p.__dict__.get("label_text", p.name) for p in model.convolve.parameters_all]
    assert labels[:7] == [
        "n<sub>0</sub>",
        "dt",
        "rep",
        "stop",
        "IRF<sub>start</sub>",
        "IRF<sub>stop</sub>",
        "lb",
    ]
    labels = [p.__dict__.get("label_text", p.name) for p in model.generic.parameters_all]
    assert labels == ["sc", "bg", "tBg", "tMeas", "#Ph<sub>B</sub>", "#Ph<sub>F</sub>"]


def test_add_and_del_change_the_lifetimes(lifetime, qapp):
    from qtpy import QtWidgets

    _fit_, model, editor = lifetime
    add = next(b for b in editor.findChildren(QtWidgets.QToolButton) if b.text() == "add")
    before = model.structure
    add.click()
    qapp.processEvents()
    assert model.structure != before and len(model.lifetimes._lifetime_parameter_rows()) == 4
    delete = next(b for b in editor.findChildren(QtWidgets.QToolButton) if b.text() == "del")
    delete.click()
    assert len(model.lifetimes._lifetime_parameter_rows()) == 2


def test_type_and_convolve_write_the_scalars(lifetime):
    from qtpy import QtWidgets

    _fit_, model, editor = lifetime
    radios = {r.text(): r for r in editor.findChildren(QtWidgets.QRadioButton)}
    radios["exp"].setChecked(True)
    assert model.get_scalar("periodic_excitation") == 0.0 and model.convolve.mode == "exp"
    radios["per"].setChecked(True)
    assert model.get_scalar("periodic_excitation") == 1.0
    convolve = _toggle(editor, "do_convolution")
    convolve.setChecked(not convolve.isChecked())
    assert bool(model.get_scalar("convolve")) == convolve.isChecked()


def test_scalar_rows_edit_the_description_scalars(lifetime):
    _fit_, model, editor = lifetime
    _edit(editor, "rep", 10.0)
    assert model.get_scalar("period") == pytest.approx(100.0)
    _edit(editor, "tBg", 2.5)
    assert model.get_scalar("t_background") == pytest.approx(2.5)
    _edit(editor, "irf_stop", 10.0)
    assert model.get_scalar("response_stop") == pytest.approx(10.0)


def test_corrections_switches(lifetime):
    from qtpy import QtWidgets

    from chisurf.gui.autoform.sections.builtin import ChoiceWidget

    _fit_, model, editor = lifetime
    smoothing = next(
        c for c in editor.findChildren(ChoiceWidget) if c._section.attr == "window_function"
    )
    smoothing.combo.setCurrentText("blackman")
    assert model.get_scalar("lin_window") == 4.0
    pile_up = next(c for c in editor.findChildren(QtWidgets.QCheckBox) if c.text() == "Pile-up")
    pile_up.setChecked(True)
    assert model.get_scalar("pile_up") == 1.0


def test_abs_and_norm_write_the_amplitude_scalars(lifetime):
    from qtpy import QtWidgets

    _fit_, model, editor = lifetime
    boxes = {c.text(): c for c in editor.findChildren(QtWidgets.QCheckBox)}
    boxes["Norm."].click()
    assert model.get_scalar("normalize_amplitudes") == 0.0
    boxes["Abs."].click()
    assert model.get_scalar("absolute_amplitudes") == 0.0


def test_polarization_is_the_description_scalar(lifetime):
    from chisurf.gui.autoform.sections.builtin import ChoiceWidget

    _fit_, model, editor = lifetime
    choice = next(
        c for c in editor.findChildren(ChoiceWidget) if c._section.attr == "polarization_type"
    )
    choice.combo.setCurrentText("vv")
    assert model.get_scalar("polarization") == 1.0
    assert model.anisotropy.polarization_type == "vv"


def test_the_irf_loads_and_unloads_through_the_classic_actions(lifetime):
    fit, model, _editor = lifetime
    cs.imported_datasets.append(DataCurve(x=model.x, y=np.ones_like(model.x), name="flat-irf"))
    try:
        cs.core.actions.dispatch(
            name="model.change_irf",
            payload={
                "irf_idx": len(cs.imported_datasets) - 1,
                "irf_name": "flat-irf",
                "fit_index": cs.fits.index(fit),
            },
        )
        assert model.convolve.irf is not None and np.allclose(model.convolve.irf.y, 1.0)
        cs.core.actions.dispatch(name="model.unload_irf", payload={"fit_index": cs.fits.index(fit)})
        assert model.convolve.irf is None
    finally:
        cs.imported_datasets.pop()


def test_the_fret_editor_has_the_classic_panels_and_controls(qapp):
    from qtpy import QtWidgets

    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit, model = _fit("tcspc_fret_gaussian")
    cs.fits.append(fit)
    try:
        editor = build_model_editor(model)
        editor.show()
        qapp.processEvents()
        assert _panels(editor)[:7] == [
            "Convolution",
            "Generic",
            "Corrections",
            "Donor",
            "FRET parameters",
            "Gaussian distances",
            "Anisotropy",
        ]
        assert [p.name for p in model.fret_parameters.parameters_all][-1] == "E_FRET"
        static = next(
            r for r in editor.findChildren(QtWidgets.QRadioButton) if r.text() == "static κ²"
        )
        static.setChecked(True)
        assert model.get_scalar("static_orientation") == 1.0
        between = _toggle(editor, "is_distance_between_gaussians")
        between.setChecked(True)
        assert model.get_scalar("distance_between_gaussians") == 1.0
        before = len(model.gaussians._gaussian_parameter_rows())
        model.gaussians.append_gaussian()
        assert len(model.gaussians._gaussian_parameter_rows()) == before + 4
        density, axis = model.distance_distribution[0]
        assert density.size == axis.size > 0
    finally:
        cs.fits.remove(fit)


def test_the_classic_rows_are_not_fitted(lifetime):
    """dt, rep, tBg and the photon counts are rows of the editor, never fit parameters."""
    _fit_, model, _editor = lifetime
    fitted = {p.name for p in model.parameters_all}
    assert not {"dt", "rep", "stop", "tBg", "tMeas", "PhB", "PhF", "tDead", "win-size"} & fitted
