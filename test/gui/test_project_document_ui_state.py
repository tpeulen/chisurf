"""Actual Main ordinary Save/restoration must retain per-fit view state."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_actual_main_ordinary_save_preserves_plot_context(request, tmp_path, monkeypatch):
    """Use isolated native processes for the real document capture/publication path."""
    if os.environ.get("CHISURF_DOCUMENT_UI_CHILD") != "1":
        env = os.environ.copy()
        env["CHISURF_DOCUMENT_UI_CHILD"] = "1"
        env["CHISURF_SETTINGS_DIR"] = str(tmp_path / "settings")
        env["MMFDB_SETTINGS_DIR"] = str(tmp_path / "mmfdb")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                request.node.nodeid,
                "-q",
                "--tb=short",
                f"--basetemp={tmp_path / 'native'}",
                f"--junitxml={tmp_path / 'native.xml'}",
                "-p",
                "no:cacheprovider",
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        (tmp_path / "native.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / "native.xml").is_file()
        return

    import numpy as np
    from qtpy import QtCore, QtWidgets

    import chisurf as cs
    import chisurf.gui as cs_gui
    from chisurf.core.experiments.tcspc.reader import TCSPCReader
    from chisurf.core.project.lifecycle import SaveDecision
    from chisurf.core.project.project import ResourceContext
    from chisurf.core.project.storage import load_file
    from chisurf.core.project.ui_state import get_ui_state
    from chisurf.gui.main import Main
    from chisurf.gui.plots.lineplot.lineplot import LinePlot
    from chisurf.macros.core_fit import get_project_payload, load_project, save_project
    from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class IsolatedSettings(QtCore.QSettings):
        """Use only the temporary test settings, not user preferences."""

        def __init__(self, *args, **kwargs):
            super().__init__(str(tmp_path / "main.ini"), QtCore.QSettings.IniFormat)

    monkeypatch.setattr(QtCore, "QSettings", IsolatedSettings)
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(cs, "project_resources", ResourceContext(), raising=False)
    monkeypatch.setattr(cs_gui, "fit_windows", [])
    if getattr(cs, "console", None) is None:
        cs.console = cs_gui.widgets.ipython.QIPythonWidget()
        cs.console.history_widget = None
    main = Main()
    monkeypatch.setattr(cs, "cs", main)
    main.resize(1500, 950)
    main.init_setups()
    main.define_actions()
    main.arrange_widgets()
    main.show()
    monkeypatch.setattr(main, "_save_decision", lambda: SaveDecision.DISCARD)

    fit = _simulated_fit()
    experiment = cs.experiment["TCSPC"]
    reader = TCSPCReader(record_provenance=False)
    experiment.add_reader(reader)
    for member in fit.grouped_fits:
        member.data.experiment = experiment
        member.data.data_reader = reader
    cs.fits.append(fit)
    cs.imported_datasets.extend(member.data for member in fit.grouped_fits)
    main._open_fit_subwindow(fit)
    main.dataset_selector.update()
    main.fit_selector.update()
    app.processEvents()
    window = main.mdiarea.subWindowList()[0]
    window.setGeometry(70, 60, 840, 610)
    # Visit the plot that owns the actual retained controller.
    plot = next(p for p in window._created_plots if isinstance(p, LinePlot))
    state = plot.get_settings_state()
    # Exercise real saved controller options, rather than inventing option names.
    boolean_keys = [key for key, value in state.items() if type(value) is bool]
    assert boolean_keys, state
    state[boolean_keys[0]] = not state[boolean_keys[0]]
    plot.set_settings_state(state)
    app.processEvents()
    expected = get_ui_state(main)["fit_windows"][fit.unique_identifier]
    before_ranges = [(member.xmin, member.xmax) for member in fit.grouped_fits]
    before_parameters = [
        [p.value for p in member.model.parameters_all] for member in fit.grouped_fits
    ]
    main.grab().save(str(tmp_path / "before-ui.png"))

    project = get_project_payload("retained GUI model state")
    destination = save_project(str(tmp_path / "gui-state.cs.pto"))
    readback = load_file(destination)
    assert project.ui_state["fit_windows"][fit.unique_identifier] == expected
    assert readback.ui_state["fit_windows"][fit.unique_identifier] == expected
    result = load_project(str(destination))
    assert result["ok"] is True, result
    app.processEvents()
    restored_window = main.mdiarea.subWindowList()[0]
    assert restored_window is not window
    actual = get_ui_state(main)["fit_windows"][fit.unique_identifier]
    assert actual["current_plot_index"] == expected["current_plot_index"]
    assert actual["plots"] == expected["plots"]
    restored_fit = cs.fits[0]
    assert [(member.xmin, member.xmax) for member in restored_fit.grouped_fits] == before_ranges
    for member, params in zip(restored_fit.grouped_fits, before_parameters):
        np.testing.assert_allclose([p.value for p in member.model.parameters_all], params)
    assert main.grab().save(str(tmp_path / "restored-ui.png"))
    second = save_project(str(tmp_path / "gui-state-second.cs.pto"))
    assert (
        load_file(second).ui_state["fit_windows"][fit.unique_identifier]["plots"]
        == expected["plots"]
    )
    main.hide()
