"""Vector constants through the Qt window's calibration paths.

Opening a measurement restores its stored constants, *Load calibration*
applies a saved one, and a run writes its result: each goes through the
window's parameter table (:class:`ndxplorer.ui.parameter_editor.ParameterEditor`)
and each carries the per-population factors (vector constants) as the emtk app
does. A run that kept one shared γ replaces a stale γ vector.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")

from ndxplorer.core.equation_graph import constant_vectors  # noqa: E402

STORED = {
    "values": [0.4536, 0.8090],
    "populations": ["FRET 1", "FRET 2"],
    "uncertainties": {"FRET 1": 0.01, "FRET 2": 0.02},
    "column": "Population",
}


@pytest.fixture
def ndx(qapp):
    """An ndX stand-in whose constants are its parameter table's group."""
    from ndxplorer.core.data_source import DataSource
    from ndxplorer.ui.parameter_editor import ParameterEditor

    rng = np.random.default_rng(0)
    n = 3000
    kind = rng.choice([0, 1, 2], n, p=[0.25, 0.15, 0.60])
    E = np.where(kind == 2, rng.normal(0.55, 0.08, n), np.where(kind == 0, 0.02, 0.0))
    S = np.where(kind == 0, 0.95, np.where(kind == 1, 0.08, 0.55))
    size = rng.gamma(4.0, 60.0, n)
    columns = {
        "Number of Photons (green)": np.clip(size * (1 - E) * S, 1, None),
        "Number of Photons (red)": np.clip(size * E * S, 1, None),
        "Number of Photons (yellow)": np.clip(size * (1 - S), 1, None),
    }

    class _Ndx:
        def __init__(self):
            self.data_source = DataSource.from_columns(columns)
            self.parameter_control = ParameterEditor()
            editor = self.parameter_control
            self.constants = editor._cg.ConstantsMapping(editor._group)

    window = _Ndx()
    yield window
    window.parameter_control.close()


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_opening_a_measurement_restores_its_stored_vector(ndx, tmp_path, monkeypatch):
    from ndxplorer.io import fret_calibration_io

    from chisurf.plugins.ndxplorer.calibration_bridge import restore_calibration_from_container

    container = tmp_path / "cal1.pto"
    container.write_bytes(b"")
    monkeypatch.setattr(
        fret_calibration_io,
        "restorable",
        lambda path: {"saved": {"alpha": 0.07}, "background": {}, "vectors": {"gamma": STORED}},
    )
    applied = restore_calibration_from_container(ndx, str(container))
    editor = ndx.parameter_control
    assert editor._group.get("gamma").populations == ["FRET 1", "FRET 2"]
    assert ndx.constants["gamma[FRET 2]"] == pytest.approx(0.8090)
    assert applied["gamma[FRET 1]"] == pytest.approx(0.4536) and applied["alpha"] == 0.07
    assert "gamma" in constant_vectors(ndx.constants)
    assert editor._cg.vector_axis(editor._group, "gamma").column == "Population"
    names = [
        editor._table.table_model.index(r, 0).data()
        for r in range(editor._table.table_model.rowCount())
    ]
    assert any(str(n).endswith("gamma [2]") for n in names)


def test_load_calibration_applies_its_vector(ndx):
    """The Load calibration route: the saved constants and vectors, one push."""
    from chisurf.plugins.ndxplorer.calibration_bridge import _push_constants

    _push_constants(ndx, {"alpha": 0.06}, vectors={"gamma": STORED})
    assert ndx.constants["alpha"] == pytest.approx(0.06)
    assert ndx.parameter_control.dict["gamma[FRET 1]"] == pytest.approx(0.4536)


def test_a_shared_run_replaces_the_stale_vector(ndx):
    from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

    ndx.parameter_control.apply_vectors({"gamma": STORED})
    result = optimize_calibration_from_ndx(
        ndx, n_bootstrap=0, inject_columns=False, recompute=False, species_factors="off"
    )
    assert result["ok"], result.get("error")
    assert result["replaced_vectors"] == ["gamma"]
    assert "Replaced population-wise γ with shared γ" in result["report"]
    assert not ndx.parameter_control._group.get("gamma").is_vector
    assert "gamma" not in constant_vectors(ndx.constants)
    assert ndx.constants["gamma"] == pytest.approx(result["factors"]["gamma"])
