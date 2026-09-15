"""A real fitting-window round trip through the ``.cs.pto`` project format."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("qtpy")

import chisurf as cs
import chisurf.gui as cs_gui
from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.fluorescence.decay import synthetic_decay
from chisurf.core.fluorescence.tcspc.irf import synthetic_irf
from chisurf.core.models.description import tcspc_lifetime as LifetimeModel
from chisurf.gui.widgets.fitting import FittingControllerWidget, FitSubWindow
from chisurf.macros.core_fit import load_project, save_project


def _simulated_fit() -> FitGroup:
    dt = 0.048
    time = np.arange(256, dtype=float) * dt
    irf = synthetic_irf(time, center_ns=1.5, fwhm_ns=0.18, norm=True)
    expected = 75_000.0 * (
        0.35 * synthetic_decay(256, [0.9], bin_width=dt, irf=irf, normalize=True)
        + 0.65 * synthetic_decay(256, [3.4], bin_width=dt, irf=irf, normalize=True)
    )
    counts_a = np.random.default_rng(7).poisson(expected).astype(float)
    counts_b = np.random.default_rng(8).poisson(expected * 0.72).astype(float)
    data_a = DataCurve(
        x=time, y=counts_a, ey=np.sqrt(np.maximum(counts_a, 1.0)),
        name="simulated-tcspc-a",
    )
    data_b = DataCurve(
        x=time, y=counts_b, ey=np.sqrt(np.maximum(counts_b, 1.0)),
        name="simulated-tcspc-b",
    )
    group = FitGroup(
        data=DataCurveGroup([data_a, data_b], name="simulated-tcspc-global"),
        model_class=LifetimeModel,
    )
    group.fit_range = (18, 230)
    for local_fit in group.grouped_fits:
        model = local_fit.model
        model.set_dataset("response", DataCurve(x=time, y=irf * 1e4, name="simulated-irf"))
        model.structure = "lifetime.components.2"
        values = {p.canonical_id: p for p in model.parameters_all}
        for canonical, value in (("lifetime.tau.0", 1.1), ("lifetime.tau.1", 3.1),
                                 ("lifetime.amplitude.0", 0.4), ("lifetime.amplitude.1", 0.6)):
            values[canonical].value = value
    group.update()
    return group


def _window(fit: FitGroup, qtbot):
    from qtpy import QtWidgets

    controls_host = QtWidgets.QWidget()
    controls_layout = QtWidgets.QVBoxLayout(controls_host)
    controller = FittingControllerWidget(fit=fit)
    window = FitSubWindow(fit=fit, control_layout=controls_layout, fit_widget=controller)
    window.setWindowTitle(fit.name)
    window.resize(1050, 720)
    qtbot.addWidget(controls_host)
    qtbot.addWidget(controller)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(150)
    return window


def _capture(window, name: str, tmp_path: Path) -> Path:
    artifact_dir = Path(os.environ.get("CHISURF_VISUAL_ARTIFACT_DIR", tmp_path))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / name
    assert window.grab().save(str(path))
    assert path.stat().st_size > 0
    return path


def _input_parameter_values(model) -> dict[str, float]:
    values = {}
    for parameter in model.parameters_all:
        port = getattr(parameter, "_port", None)
        if port is not None and getattr(port, "get_is_output", lambda: False)():
            continue
        value = float(parameter.value)
        if not np.isfinite(value):
            continue
        values[parameter.name] = value
    return values


def test_simulated_tcspc_fit_window_survives_project_roundtrip(qapp, qtbot, tmp_path):
    old_fits = cs.fits
    old_datasets = cs.imported_datasets
    old_windows = cs_gui.fit_windows
    cs.fits = []
    cs.imported_datasets = []
    cs_gui.fit_windows = []
    try:
        fit = _simulated_fit()
        cs.fits.append(fit)
        assert len(cs.fits) == 1
        assert len(cs.fits[0].grouped_fits) == 2
        cs.imported_datasets.extend(fit.data)
        before_window = _window(fit, qtbot)
        cs_gui.fit_windows.append(before_window)
        before_image = _capture(before_window, "tcspc-project-before.png", tmp_path)

        expected_y = np.asarray(fit.grouped_fits[0].data.y).copy()
        expected_range = tuple(fit.fit_range)
        expected_member_count = len(fit.grouped_fits)
        expected_parameters = _input_parameter_values(fit.grouped_fits[0].model)
        expected_model_y = np.asarray(fit.grouped_fits[0].model.y).copy()
        project_path = save_project(str(tmp_path), "tcspc-roundtrip")
        assert project_path.name == "tcspc-roundtrip.cs.pto"

        before_window.close()
        cs_gui.fit_windows.clear()
        cs.fits.clear()
        cs.imported_datasets.clear()
        load_project(str(project_path))

        assert len(cs.fits) == 1, [
            (fit_group.name, len(fit_group.grouped_fits)) for fit_group in cs.fits
        ]
        restored = cs.fits[0]
        assert len(restored.grouped_fits) == expected_member_count
        assert restored.name == fit.name
        assert tuple(restored.fit_range) == expected_range
        np.testing.assert_allclose(restored.grouped_fits[0].data.y, expected_y)
        restored.update()
        restored_parameters = _input_parameter_values(restored.grouped_fits[0].model)
        for name, value in expected_parameters.items():
            assert name in restored_parameters
            assert restored_parameters[name] == pytest.approx(value), name
        np.testing.assert_allclose(
            restored.grouped_fits[0].model.y,
            expected_model_y,
            rtol=1e-10,
            atol=1e-10,
        )

        after_window = _window(restored, qtbot)
        cs_gui.fit_windows.append(after_window)
        after_image = _capture(after_window, "tcspc-project-after.png", tmp_path)
        assert before_image.read_bytes() != b""
        assert after_image.read_bytes() != b""
        assert after_window.size() == before_window.size()
    finally:
        cs.fits = old_fits
        cs.imported_datasets = old_datasets
        cs_gui.fit_windows = old_windows


def test_main_window_recreates_tcspc_fit_window_from_project(
    qapp, qtbot, tmp_path, monkeypatch
):
    from qtpy import QtCore
    from chisurf.gui.main import Main

    settings_path = tmp_path / "MainWindow.ini"

    class IsolatedSettings(QtCore.QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(str(settings_path), QtCore.QSettings.IniFormat)

    monkeypatch.setattr(QtCore, "QSettings", IsolatedSettings)
    if getattr(cs, "console", None) is None:
        cs.console = cs_gui.widgets.ipython.QIPythonWidget()
        cs.console.history_widget = None

    old_main = getattr(cs, "cs", None)
    old_fits = cs.fits
    old_datasets = cs.imported_datasets
    old_windows = cs_gui.fit_windows
    cs.fits = []
    cs.imported_datasets = []
    cs_gui.fit_windows = []
    main = Main()
    main._save_window_state = lambda: None
    qtbot.addWidget(main)
    main.resize(1500, 950)
    main.init_setups()
    main.define_actions()
    main.arrange_widgets()
    main.show()
    cs.cs = main
    qapp.processEvents()
    try:
        fit = _simulated_fit()
        cs.fits.append(fit)
        cs.imported_datasets.extend(fit.data)
        main._open_fit_subwindow(fit)
        qapp.processEvents()
        assert len(main.mdiarea.subWindowList()) == 1
        _capture(main, "tcspc-main-before.png", tmp_path)

        project_path = save_project(str(tmp_path), "tcspc-main-roundtrip")
        from chisurf.core.project import ProjectArchive
        import json
        saved_archive = ProjectArchive.open(project_path)
        saved_payload = json.loads(saved_archive.read_text("project.json"))
        saved_archive.close()
        assert len(saved_payload["fits"]) == 1
        assert len(saved_payload["fits"][0]["local_fits"]) == 2
        assert saved_payload["fits"][0]["data_group_name"] == "simulated-tcspc-global"
        expected_range = tuple(fit.fit_range)
        expected_member_count = len(fit.grouped_fits)
        expected_group_name = fit.name
        expected_members = [
            {
                "name": member.data.name,
                "data": np.asarray(member.data.y).copy(),
                "parameters": _input_parameter_values(member.model),
                "model": np.asarray(member.model.y).copy(),
            }
            for member in fit.grouped_fits
        ]

        main._close_all_fit_subwindows()
        cs.fits.clear()
        cs.imported_datasets.clear()
        cs_gui.fit_windows.clear()
        load_project(str(project_path))
        qapp.processEvents()

        assert len(cs.fits) == 1, [
            (fit_group.name, len(fit_group.grouped_fits)) for fit_group in cs.fits
        ]
        assert len(cs.fits[0].grouped_fits) == expected_member_count
        assert cs.fits[0].name == expected_group_name
        assert tuple(cs.fits[0].fit_range) == expected_range
        for restored_member, expected_member in zip(
            cs.fits[0].grouped_fits, expected_members
        ):
            assert restored_member.data.name == expected_member["name"]
            np.testing.assert_allclose(restored_member.data.y, expected_member["data"])
            restored_member.update()
            for name, value in expected_member["parameters"].items():
                assert _input_parameter_values(restored_member.model)[name] == pytest.approx(value)
            np.testing.assert_allclose(
                restored_member.model.y,
                expected_member["model"],
                rtol=1e-10,
                atol=1e-10,
            )
        assert len(main.mdiarea.subWindowList()) == 1
        assert len(cs_gui.fit_windows) == 1
        assert cs_gui.fit_windows[0].fit is cs.fits[0]
        _capture(main, "tcspc-main-after.png", tmp_path)
    finally:
        main.hide()
        cs.cs = old_main
        cs.fits = old_fits
        cs.imported_datasets = old_datasets
        cs_gui.fit_windows = old_windows
