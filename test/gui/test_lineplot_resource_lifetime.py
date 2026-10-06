"""A fit window replaced by a project load, and the one *Plot settings* dock.

Plot settings used to be one Qt controller widget per plot, hosted in the main
window's options dock, and these tests guarded those widgets' lifetimes. The
settings are now one emtk surface the dock keeps (``PlotSettingsHost``) showing
the current page; what can still go wrong is that dock going on drawing a page
whose window a project load retired -- or losing the original's page when the
load is rolled back.
"""

import os
import subprocess
import sys
from pathlib import Path

from qtpy import QtCore

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
    settings = original.plot_settings
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
        assert not is_deleted(settings)
        assert settings.page is None or settings.page in original._created_plots
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
        # A successful load retires the replaced window at once, and the dock no
        # longer draws its page; the event loop that would deliver anything still
        # queued for them runs clean.
        assert is_deleted(original)
        assert settings.owner is replacement
        assert settings.page in replacement._created_plots
        qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        qtbot.wait(30)
        assert cs_gui.fit_windows == [replacement]
        _capture(main, f"plot-lifetime-after-{attempt}.png", tmp_path)
        fit = restored
        original = replacement
        plot = next(p for p in original._created_plots if isinstance(p, LinePlot))
        # the dock is the main window's: the same surface, now on the new window
        assert not is_deleted(settings) and original.plot_settings is settings
    main.hide()
    main.deleteLater()
    qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    qapp.processEvents()
