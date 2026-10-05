"""Rich AutoForm matrix edits must preserve live, not cached, scientific values."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from qtpy import QtCore, QtTest, QtWidgets

from chisurf.core.dataspec import load_view_spec
from chisurf.core.fitting.kinetics import RateMatrixParameters
from chisurf.gui.autoform import AutoForm
from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget


@pytest.fixture(scope="session")
def qapp():
    """Keep the actual Qt application alive across rich-editor test modules."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class RateHost:
    """Expose the same rate group and data paths as scientific kinetic models."""

    def __init__(self):
        self.scheme = RateMatrixParameters(n_states=3, default_rate=0.0)
        self.scheme.rates_by_name()["k1_2"].value = 123.456
        self.scheme.rates_by_name()["k2_1"].value = 2_500_000.0

    def view_spec(self):
        """Declare the existing rich editor without owning any Qt object."""
        return load_view_spec(
            {
                "sections": [
                    {
                        "type": "custom",
                        "key": "rate_matrix",
                        "target": "scheme.rate_values",
                        "options": {
                            "size_attr": "scheme.n_states",
                            "decimals": 2,
                            "maximum": 1_000_000.0,
                            "title": "Live transition rates",
                        },
                    }
                ]
            }
        )


def _capture(form, qapp, name):
    """Capture matching normal/constrained instances when evidence is requested."""
    directory = os.environ.get("CHISURF_RATE_CAPTURE_DIR")
    if not directory:
        return
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    scroll = getattr(form, "_evidence_scroll", None)
    if scroll is None:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form)
        form._evidence_scroll = scroll
    for width, height in ((620, 900), (360, 600)):
        scroll.resize(width, height)
        scroll.show()
        qapp.processEvents()
        QtTest.QTest.qWait(30)
        assert scroll.grab().save(str(destination / f"{name}-{width}x{height}.png"))
    scroll.hide()


def test_editing_one_cell_preserves_an_external_rate_change(qapp):
    """A stale grid must not revert a rate changed after its last refresh."""
    host = RateHost()
    parameters = host.scheme.rates_by_name()
    identities = {name: (id(p), p.unique_identifier, p.fixed) for name, p in parameters.items()}
    form = AutoForm(host)
    grid = form.findChild(RateMatrixWidget)
    _capture(form, qapp, "initial")
    parameters["k1_2"].value = 432.19876
    parameters["k2_1"].value = 5_000_000.0
    # User edits only k3_2. The other cells still display their earlier values.
    grid._spins[(2, 1)].setValue(70.0)
    _capture(form, qapp, "edited")
    assert parameters["k3_2"].value == 70.0
    assert parameters["k1_2"].value == 432.19876
    assert parameters["k2_1"].value == 5_000_000.0
    assert identities == {
        name: (id(p), p.unique_identifier, p.fixed)
        for name, p in host.scheme.rates_by_name().items()
    }
    assert grid._spins[(0, 1)].value() == pytest.approx(432.20)
    form.close()


def test_editing_one_cell_preserves_a_linked_rate_and_its_source(qapp):
    """Refreshing a dependent cell is not permission to edit its source."""
    from chisurf.core.fitting.parameter import FittingParameter

    host = RateHost()
    target = host.scheme.rates_by_name()["k1_2"]
    source = FittingParameter(name="external-rate", value=123.456, fixed=False)
    target.link = source
    form = AutoForm(host)
    grid = form.findChild(RateMatrixWidget)
    source.value = 654.321
    grid._spins[(2, 1)].setValue(71.0)
    assert target.link is source
    assert source.value == 654.321
    assert target.value == 654.321
    assert grid._checkboxes[(0, 1)].checkState() == QtCore.Qt.PartiallyChecked
    assert host.scheme.rates_by_name()["k3_2"].value == 71.0
    form.close()


def test_rate_metadata_controls_bind_to_the_real_parameter(qapp):
    """A nested matrix path must retain fixed/free and detail/link controls."""
    host = RateHost()
    parameters = host.scheme.rates_by_name()
    parameters["k1_2"].fixed = False
    form = AutoForm(host)
    grid = form.findChild(RateMatrixWidget)
    assert grid._get_cell_parameter(0, 1) is parameters["k1_2"]
    assert not grid._checkboxes[(0, 1)].isChecked()
    # The real checkbox changes only its own parameter's fitted/free status.
    QtTest.QTest.mouseClick(grid._checkboxes[(0, 1)], QtCore.Qt.LeftButton)
    assert parameters["k1_2"].fixed is True
    assert parameters["k3_2"].fixed is True
    form.close()


def test_parameter_detail_actions_refresh_the_matrix(qapp):
    """The shared parameter-detail controller must refresh its originating cell."""
    from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterProxyController

    host = RateHost()
    form = AutoForm(host)
    grid = form.findChild(RateMatrixWidget)
    controller = grid.table.cellWidget(0, 1).findChild(FittingParameterProxyController)
    assert controller is not None
    host.scheme.rates_by_name()["k1_2"].value = 654.321
    controller.finalize()
    assert grid._spins[(0, 1)].value() == 654.32
    form.close()


def test_live_parameter_metadata_refreshes_every_cell_tooltip(qapp):
    """Value, fitted bounds/status and link details cannot stay at build time."""
    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterProxyController

    host = RateHost()
    form = AutoForm(host)
    grid = form.findChild(RateMatrixWidget)
    parameter = host.scheme.rates_by_name()["k1_2"]
    cell = grid.table.cellWidget(0, 1)
    spin = grid._spins[(0, 1)]
    checkbox = grid._checkboxes[(0, 1)]
    parameter.value = 654.321
    parameter.fixed = False
    parameter.bounds = (11.0, 700.0)
    grid.refresh()
    for control in (cell, spin, checkbox):
        assert "654.3" in control.toolTip()
        assert "Free [11, 700]" in control.toolTip()

    source = FittingParameter(name="external-rate", value=333.333, fixed=False)
    parameter.link = source
    cell.findChild(FittingParameterProxyController).finalize()
    for control in (cell, spin, checkbox):
        assert "333.3" in control.toolTip()
        assert "Linked" in control.toolTip()
    assert parameter.link is source
    form.close()


def test_range_warning_clears_when_live_value_returns_inside_display_range(qapp):
    """A previous clamped display must not leave a misleading warning behind."""
    host = RateHost()
    form = AutoForm(host)
    grid = form.findChild(RateMatrixWidget)
    spin = grid._spins[(1, 0)]
    assert "outside the range" in spin.toolTip()
    host.scheme.rates_by_name()["k2_1"].value = 42.0
    grid.refresh()
    assert "outside the range" not in spin.toolTip()
    assert "42" in spin.toolTip()
    assert "k2_1" in spin.toolTip()
    form.close()


def test_measured_fcs_cell_edit_recomputes_science_and_roundtrips(qapp, tmp_path):
    """Rich editor → active measured kinetics → canonical portable project."""
    import numpy as np

    from chisurf.core.project.session import capture_session, restore_session
    from chisurf.core.project.storage import load_file, save_file
    from chisurf.gui.widgets.models.model_editor import build_model_editor
    from test.project.test_fcs_snapshot_science_edits import (
        _measured_fcs_fit,
        configure_fcs_science,
        fcs_scientific_observables,
    )

    fit = _measured_fcs_fit("FCSKineticsModel")
    configure_fcs_science(fit.model)
    fit.model.update()
    initial = fcs_scientific_observables(fit.model)
    editor = build_model_editor(fit.model)
    grids = editor.findChildren(RateMatrixWidget)
    grid = next(g for g in grids if g._attr == "saturation.dark.rate_values")
    original = capture_session([fit.data], [fit])
    # Real keyboard input commits k3_1, which controls dark-state recovery.
    spin = grid._spins[(2, 0)]
    spin.setFocus()
    spin.selectAll()
    QtTest.QTest.keyClicks(spin, "750")
    QtTest.QTest.keyClick(spin, QtCore.Qt.Key_Return)
    changed = fcs_scientific_observables(fit.model)
    assert changed["prediction"] != initial["prediction"]
    assert changed["relaxation_modes"] != initial["relaxation_modes"]
    assert np.isfinite(fit.model.y).all()
    edited = capture_session([fit.data], [fit])
    assert edited.fits != original.fits
    path = save_file(edited, tmp_path / "rates.cs.pto")
    restored = restore_session(load_file(path))
    assert capture_session(restored.datasets, restored.fits).fits == edited.fits
    assert fcs_scientific_observables(restored.fits[0].model) == changed
    # Exercise the ordinary fresh-interpreter scientific readback, including
    # the probe's denial of the original resource paths.
    import json
    import subprocess
    import sys

    from test.project.scientific_catalogue_probe import original_sources, scientific_observables

    expected = tmp_path / "expected-rates.json"
    expected.write_text(
        json.dumps(
            {
                "predictions": [np.asarray(fit.model.y).tolist()],
                "observables": [scientific_observables(fit)],
                "source_paths": sorted(original_sources(edited)),
            }
        )
    )
    result = subprocess.run(
        [sys.executable, "-m", "test.project.scientific_catalogue_probe", str(path), str(expected)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    editor.close()


def test_six_state_grid_keeps_the_last_column_reachable_when_constrained(qapp):
    """A matrix cannot hide scientific controls inside undersized cells."""
    host = RateHost()
    host.scheme.n_states = 6
    form = AutoForm(host)
    grid = form.findChild(RateMatrixWidget)
    _capture(form, qapp, "six-state")
    window = getattr(form, "_evidence_scroll", form)
    window.resize(360, 600)
    window.show()
    qapp.processEvents()
    bar = grid.table.horizontalScrollBar()
    assert bar.isVisible() and bar.maximum() > 0
    bar.setValue(bar.maximum())
    qapp.processEvents()
    QtTest.QTest.qWait(30)
    cell = grid.table.cellWidget(5, 5)
    assert grid.table.viewport().rect().contains(cell.geometry())
    directory = os.environ.get("CHISURF_RATE_CAPTURE_DIR")
    if directory:
        assert window.grab().save(str(Path(directory) / "six-state-last-column-360x600.png"))
    window.close()
