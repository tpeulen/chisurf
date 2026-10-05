"""Real Qt callback lifetimes across externally hosted plot-control disposal."""

import os
import subprocess
import sys
from pathlib import Path

from qtpy import QtCore, QtWidgets

from chisurf.gui.plots.lineplot.lineplot import LinePlot
from chisurf.gui.qt_lifetime import is_deleted
from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit


def _native_process(node, tmp_path):
    """Run each resource scenario in a fresh real native-renderer process."""
    if os.environ.get("CHISURF_PLOT_LIFETIME_CHILD") == "1":
        return False
    env = os.environ.copy()
    env["CHISURF_PLOT_LIFETIME_CHILD"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            f"{__file__}::{node}",
            "-q",
            "-s",
            "--tb=short",
            f"--basetemp={tmp_path / 'native'}",
            f"--junitxml={tmp_path / 'native.xml'}",
            "-p",
            "no:cacheprovider",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        timeout=150,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "native.xml").is_file(), result.stdout + result.stderr
    return True


def test_control_host_destruction_retires_pending_plot_update(qapp, qtbot, tmp_path):
    """An external controls host can die before a window-owned update fires."""
    if _native_process("test_control_host_destruction_retires_pending_plot_update", tmp_path):
        return
    fit = _simulated_fit()
    plot = LinePlot(fit)
    qtbot.addWidget(plot)
    host = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(host)
    layout.addWidget(plot.plot_controller)
    plot.update()
    checkbox = plot.plot_controller.checkBox
    timer = QtCore.QTimer(plot)
    timer.setSingleShot(True)
    timer.timeout.connect(plot.update)
    delivered = []
    timer.timeout.connect(lambda: delivered.append(True))
    timer.start(0)

    host.deleteLater()
    qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    assert is_deleted(checkbox)
    assert not is_deleted(plot)
    qtbot.waitUntil(lambda: bool(delivered))


def test_plot_destruction_disposes_externally_hosted_controls(qapp, qtbot, tmp_path):
    """Controls reparented out of a plot must not survive their logical owner."""
    if _native_process("test_plot_destruction_disposes_externally_hosted_controls", tmp_path):
        return
    plot = LinePlot(_simulated_fit())
    host = QtWidgets.QWidget()
    qtbot.addWidget(host)
    layout = QtWidgets.QVBoxLayout(host)
    controller = plot.plot_controller
    layout.addWidget(controller)
    timer = QtCore.QTimer(host)
    timer.setSingleShot(True)
    timer.timeout.connect(plot.update)
    delivered = []
    timer.timeout.connect(lambda: delivered.append(True))
    timer.start(0)
    plot.deleteLater()
    qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    assert is_deleted(plot)
    qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    assert is_deleted(controller)
    qtbot.waitUntil(lambda: bool(delivered))


def test_detached_controls_remain_live_for_rollback(qapp, qtbot, tmp_path, monkeypatch):
    """Temporary removal/hiding must not retire the original plot or its controls."""
    if _native_process("test_detached_controls_remain_live_for_rollback", tmp_path):
        return
    plot = LinePlot(_simulated_fit())
    host = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(host)
    controller = plot.plot_controller
    layout.addWidget(controller)
    controller.hide()
    layout.removeWidget(controller)
    controller.setParent(None)
    timer = QtCore.QTimer(plot)
    timer.setSingleShot(True)
    timer.timeout.connect(plot.update)
    timer.start(0)
    qtbot.wait(20)
    assert plot.plot_controller is controller
    assert not is_deleted(controller.checkBox)
    layout.addWidget(controller)
    controller.show()
    controller.checkBox.setChecked(True)
    assert plot.plot_controller.data_is_log_y

    def broken_curves():
        """Represent a genuine scientific failure in an otherwise live plot."""
        raise ValueError("live curve failure")

    import pytest

    monkeypatch.setattr(plot.fit, "get_curves", broken_curves)
    with pytest.raises(ValueError, match="live curve failure"):
        plot.update()
    plot.deleteLater()
    host.deleteLater()
    qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    qapp.processEvents()


def test_tcspc_replacement_rollback_and_retired_callbacks(qapp, qtbot, tmp_path, monkeypatch):
    """Real replacements preserve rollback controls and retire disposed old views."""
    if _native_process("test_tcspc_replacement_rollback_and_retired_callbacks", tmp_path):
        return
    import numpy as np
    import pytest

    import chisurf as cs
    import chisurf.gui as cs_gui
    from chisurf.core.data import DataCurveGroup
    from chisurf.core.experiments.tcspc.reader import TCSPCReader
    from chisurf.gui.main import Main
    from chisurf.macros.core_fit import load_project, save_project
    from test.gui.test_tcspc_project_visual_roundtrip import _capture

    class IsolatedSettings(QtCore.QSettings):
        """Keep native window settings inside the test's scratch directory."""

        def __init__(self, *args, **kwargs):
            """Bind the existing QSettings API to an isolated real INI file."""
            super().__init__(str(tmp_path / "MainWindow.ini"), QtCore.QSettings.IniFormat)

    monkeypatch.setattr(QtCore, "QSettings", IsolatedSettings)
    if getattr(cs, "console", None) is None:
        cs.console = cs_gui.widgets.ipython.QIPythonWidget()
        cs.console.history_widget = None
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs_gui, "fit_windows", [])
    main = Main()
    main._save_window_state = lambda: None
    main.resize(1500, 950)
    main.init_setups()
    main.define_actions()
    main.arrange_widgets()
    main.show()
    monkeypatch.setattr(cs, "cs", main)
    monkeypatch.setattr(main, "_guard_project_transition", lambda: True)
    qapp.processEvents()
    fit = _simulated_fit()
    experiment = cs.experiment["TCSPC"]
    reader = TCSPCReader(record_provenance=False)
    experiment.add_reader(reader)
    for member in fit.grouped_fits:
        member.data.experiment = experiment
        member.data.data_reader = reader
    cs.fits.append(fit)
    cs.imported_datasets.append(
        DataCurveGroup(
            [member.data for member in fit.grouped_fits],
            name=fit.name,
        )
    )
    main._open_fit_subwindow(fit)
    qapp.processEvents()
    original = cs_gui.fit_windows[0]
    plot = next(p for p in original._created_plots if isinstance(p, LinePlot))
    controller = plot.plot_controller
    expected_data = fit.grouped_fits[0].data.y.copy()
    expected_model = fit.grouped_fits[0].model.y.copy()
    project_path = save_project(str(tmp_path), "plot-lifetime-roundtrip")
    _capture(main, "plot-lifetime-before.png", tmp_path)
    open_window = main._open_fit_subwindow

    def fail_after_real_window(new_fit, **kwargs):
        """Fail presentation only after constructing its actual scientific view."""
        open_window(new_fit, **kwargs)
        raise RuntimeError("presentation acceptance failure")

    for attempt in range(2):
        monkeypatch.setattr(main, "_open_fit_subwindow", fail_after_real_window)
        with pytest.raises(RuntimeError, match="presentation acceptance failure"):
            load_project(str(project_path))
        qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        qtbot.wait(30)
        assert cs.fits[0] is fit
        assert cs_gui.fit_windows == [original]
        assert plot.plot_controller is controller
        assert not is_deleted(controller.checkBox)
        plot.update()
        _capture(main, f"plot-lifetime-rollback-{attempt}.png", tmp_path)

        monkeypatch.setattr(main, "_open_fit_subwindow", open_window)
        load_project(str(project_path))
        qtbot.wait(30)
        restored = cs.fits[0]
        assert restored is not fit
        assert restored.fit_range == fit.fit_range
        np.testing.assert_allclose(restored.grouped_fits[0].data.y, expected_data)
        np.testing.assert_allclose(restored.grouped_fits[0].model.y, expected_model)
        assert len(cs_gui.fit_windows) == 1
        replacement = cs_gui.fit_windows[0]
        assert replacement is not original
        timer = QtCore.QTimer(main)
        timer.setSingleShot(True)
        timer.timeout.connect(plot.update)
        delivered = []
        timer.timeout.connect(lambda: delivered.append(True))
        timer.start(0)
        controller.deleteLater()
        qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        assert is_deleted(controller.checkBox)
        qtbot.waitUntil(lambda: bool(delivered))
        assert plot.plot_controller is None
        original.deleteLater()
        qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        _capture(main, f"plot-lifetime-after-{attempt}.png", tmp_path)
        fit = restored
        original = replacement
        plot = next(p for p in original._created_plots if isinstance(p, LinePlot))
        controller = plot.plot_controller
    main.hide()
    main.deleteLater()
    qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    qapp.processEvents()
