"""Regression coverage for the legacy Qt acquisition window topology."""

from __future__ import annotations

import pytest
from qtpy import QtWidgets


class AcquisitionQtHost(QtWidgets.QMainWindow):
    """Small ChiSurf-shaped host that exercises the real Qt plugin entrypoint."""

    def __init__(self) -> None:
        super().__init__()
        self.mdiarea = QtWidgets.QMdiArea(self)
        self.plot_options_host = QtWidgets.QWidget(self)
        self.plotOptionsLayout = QtWidgets.QVBoxLayout(self.plot_options_host)
        self.plotOptionsLayout.setContentsMargins(0, 0, 0, 0)
        self.model_host = QtWidgets.QWidget(self)
        self.modelLayout = QtWidgets.QVBoxLayout(self.model_host)
        self.analysis_header_host = QtWidgets.QWidget(self)
        self.analysisHeaderLayout = QtWidgets.QVBoxLayout(self.analysis_header_host)
        self.current_fit = None
        self.current_fit_widget = None
        self._fit_idx = None
        self.subwindow_activation_calls = 0
        self.update_calls = 0
        self.mdiarea.subWindowActivated.connect(self.subWindowActivated)

        central = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.mdiarea)
        self.setCentralWidget(central)

    def subWindowActivated(self) -> None:
        """Run ChiSurf's production Plot Settings activation implementation."""
        from chisurf.gui.main import Main

        self.subwindow_activation_calls += 1
        Main.subWindowActivated(self)

    def update(self) -> None:
        self.update_calls += 1
        super().update()


@pytest.fixture
def qt_application():
    """Provide the one QApplication required by the offscreen Qt harness."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def qt_host(monkeypatch, qt_application):
    """Install a small active ChiSurf host and restore global dataset state."""
    import chisurf

    original_datasets = list(chisurf.imported_datasets)
    chisurf.imported_datasets[:] = []
    host = AcquisitionQtHost()
    monkeypatch.setattr(chisurf, "cs", host)
    try:
        yield host
    finally:
        host.close()
        chisurf.imported_datasets[:] = original_datasets


def test_plugin_start_creates_one_acq_fit_window_and_dataset(qt_host, qt_application):
    """Starting the Qt plugin yields one fit-style `acq` MDI surface, not a left dock."""
    import chisurf
    from chisurf.plugins.core.acq.gui.tool import SMAcquisitionManager

    manager = SMAcquisitionManager()
    qt_application.processEvents()

    assert [subwindow.windowTitle() for subwindow in qt_host.mdiarea.subWindowList()] == ["acq"]
    assert manager.acquisition_window.width() >= 750
    assert manager.acquisition_window.height() >= 600
    assert manager.acquisition_window.plot_tab_widget.currentWidget() is manager.acquisition_dock
    assert not qt_host.findChildren(QtWidgets.QDockWidget)
    assert [dataset.name for dataset in chisurf.imported_datasets] == ["acq"]
    assert qt_host.update_calls >= 1


def test_acquisition_plot_tab_drives_the_existing_plot_settings_area(qt_host, qt_application):
    """Selecting an acquisition graph supplies its controller to Plot Settings."""
    from chisurf.plugins.core.acq.gui.tool import SMAcquisitionManager

    manager = SMAcquisitionManager()
    window = manager.acquisition_window
    qt_host.mdiarea.setActiveSubWindow(window)
    qt_application.processEvents()
    activation_calls_before = qt_host.subwindow_activation_calls
    window.plot_tab_widget.setCurrentWidget(manager.decay_window)
    qt_application.processEvents()

    controller = manager.decay_window.plot_controller
    assert window.current_plot_controller is controller
    assert qt_host.subwindow_activation_calls > activation_calls_before
    assert qt_host.plotOptionsLayout.itemAt(qt_host.plotOptionsLayout.count() - 1).widget() is controller

    window.plot_tab_widget.setCurrentWidget(manager.acquisition_dock)
    qt_application.processEvents()

    assert window.current_plot_controller is None
    assert controller.isHidden()


def test_visibility_checkboxes_switch_tabs_without_creating_new_mdi_windows(
    qt_host, qt_application
):
    """The legacy Show controls now reveal tabs within the single acq window."""
    from chisurf.plugins.core.acq.gui.tool import SMAcquisitionManager

    manager = SMAcquisitionManager()
    window = manager.acquisition_window
    tabs = window.plot_tab_widget
    macrotime_index = 4

    assert tabs.count() == 6
    assert not tabs.isTabVisible(macrotime_index)
    manager.acquisition_dock.show_macrotime = True
    qt_application.processEvents()

    assert tabs.isTabVisible(macrotime_index)
    assert tabs.currentWidget() is manager.macrotime_window
    assert len(qt_host.mdiarea.subWindowList()) == 1

    manager.acquisition_dock.show_macrotime = False
    qt_application.processEvents()

    assert not tabs.isTabVisible(macrotime_index)
    assert tabs.currentWidget() is manager.acquisition_dock


def test_close_removes_unified_window_and_dummy_dataset(qt_host, qt_application, monkeypatch):
    """Closing acquisition removes its single MDI surface and its dataset sentinel."""
    import chisurf
    from chisurf.plugins.core.acq.gui import tool

    monkeypatch.setattr(
        tool.dialogs,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.Yes,
    )
    manager = tool.SMAcquisitionManager()

    manager.close_acquisition_mode()
    qt_application.processEvents()

    assert qt_host.mdiarea.subWindowList() == []
    assert chisurf.imported_datasets == []
    assert not hasattr(qt_host, "_acquisition_manager")
    assert manager.acquisition_window is None


def test_title_bar_close_runs_unified_acquisition_teardown(qt_host, qt_application, monkeypatch):
    """The acq MDI close button owns the same UI/data lifecycle as Close Mode."""
    import chisurf
    from chisurf.plugins.core.acq.gui import tool

    monkeypatch.setattr(
        tool.dialogs,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.Yes,
    )
    manager = tool.SMAcquisitionManager()
    stop_calls = []
    monkeypatch.setattr(manager, "stop_acquisition", lambda: stop_calls.append(True))

    manager.acquisition_window.title_bar.close_btn.click()
    qt_application.processEvents()

    assert stop_calls == [True]
    assert qt_host.mdiarea.subWindowList() == []
    assert chisurf.imported_datasets == []
    assert not hasattr(qt_host, "_acquisition_manager")
    assert manager.acquisition_window is None


def test_close_joins_workers_before_destroying_unified_window(qt_host, qt_application, monkeypatch):
    """Confirmed close stops both acquisition workers before it releases Qt state."""
    from chisurf.plugins.core.acq.gui import tool

    class StoppingWorker:
        def __init__(self):
            self.running = True
            self.stop_calls = 0
            self.wait_timeouts = []

        def get_results(self):
            return None

        def isRunning(self):
            return self.running

        def stop(self):
            self.stop_calls += 1
            self.running = False

        def wait(self, timeout):
            self.wait_timeouts.append(timeout)
            return True

    monkeypatch.setattr(
        tool.dialogs,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.Yes,
    )
    manager = tool.SMAcquisitionManager()
    processing_worker = StoppingWorker()
    acquisition_worker = StoppingWorker()
    setattr(manager, "_processing_thread", processing_worker)
    setattr(manager, "acquisition_thread", acquisition_worker)

    manager.close_acquisition_mode()
    qt_application.processEvents()

    assert processing_worker.stop_calls == 1
    assert processing_worker.wait_timeouts == [3000]
    assert acquisition_worker.stop_calls == 1
    assert acquisition_worker.wait_timeouts == [5000]
    assert manager.acquisition_window is None


def test_stop_blocks_restart_until_timed_out_worker_exits(qt_host, monkeypatch):
    """A timeout keeps a live worker tracked and makes starting a new run impossible."""
    from chisurf.plugins.core.acq.gui import tool

    class TimedOutWorker:
        def __init__(self):
            self.stop_calls = 0
            self.wait_timeouts = []

        def isRunning(self):
            return True

        def stop(self):
            self.stop_calls += 1

        def wait(self, timeout):
            self.wait_timeouts.append(timeout)
            return False

    manager = tool.SMAcquisitionManager()
    worker = TimedOutWorker()
    setattr(manager, "acquisition_thread", worker)

    manager.stop_acquisition()

    assert worker.stop_calls == 1
    assert worker.wait_timeouts == [5000]
    assert manager.acquisition_thread is worker
    assert not manager.acquisition_dock.start_button.isEnabled()
    assert manager.acquisition_dock.stop_button.isEnabled()

    manager.start_acquisition()

    assert manager.acquisition_thread is worker


def test_close_joins_an_already_finished_acquisition_worker(qt_host, qt_application, monkeypatch):
    """Close still joins a worker that reports finished before teardown begins."""
    from chisurf.plugins.core.acq.gui import tool

    class FinishedWorker:
        def __init__(self):
            self.stop_calls = 0
            self.wait_timeouts = []

        def isRunning(self):
            return False

        def stop(self):
            self.stop_calls += 1

        def wait(self, timeout):
            self.wait_timeouts.append(timeout)
            return True

    monkeypatch.setattr(
        tool.dialogs,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.Yes,
    )
    manager = tool.SMAcquisitionManager()
    worker = FinishedWorker()
    setattr(manager, "acquisition_thread", worker)

    manager.close_acquisition_mode()
    qt_application.processEvents()

    assert worker.stop_calls == 0
    assert worker.wait_timeouts == [5000]
    assert manager.acquisition_window is None


def test_close_ignores_late_acquisition_callbacks(qt_host, qt_application, monkeypatch):
    """Queued worker completion/error slots cannot access widgets after closing."""
    from chisurf.plugins.core.acq.gui import tool

    monkeypatch.setattr(
        tool.dialogs,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.Yes,
    )
    manager = tool.SMAcquisitionManager()

    manager.close_acquisition_mode()
    qt_application.processEvents()

    assert manager._is_closing
    manager.acquisition_completed()
    manager.acquisition_error("late worker callback")
