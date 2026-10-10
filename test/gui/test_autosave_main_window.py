"""The real main window autosaves a loaded dataset silently.

Offscreen ``Main`` with ``project.autosave.interval_s = 1``: after a dataset is
loaded and the event loop runs for a few seconds, the autosave file exists and
no modal dialog was ever opened. An explicit save then removes the autosave
copy it made obsolete.
"""

from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import utils

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
utils.set_search_paths(TOPDIR)

import pytest
from qtpy import QtWidgets
from qtpy.QtTest import QTest

import chisurf as cs
import chisurf.gui
import chisurf.macros

DECAY = "./test/data/tcspc/ibh_sample/Decay_577D.txt"


@pytest.fixture(scope="module", autouse=True)
def _ensure_app():
    # The hermetic settings directory looks like a first run, which schedules
    # the onboarding wizard (a modal). It is not what this test measures, so
    # mark it shown and close one that was already scheduled.
    cs.__startup_onboarding_shown__ = True
    app = cs.gui.get_app()
    QTest.qWait(200)
    modal = QtWidgets.QApplication.activeModalWidget()
    while modal is not None and type(modal).__name__ == "WelcomeToChiSurfWizard":
        modal.reject()
        QTest.qWait(50)
        modal = QtWidgets.QApplication.activeModalWidget()
    return app


def _load_decay():
    gui = cs.cs
    cs.core.actions.dispatch(name="fit.close_all", payload={})
    cs.imported_datasets.clear()
    gui.comboBox_experimentSelect.setCurrentIndex(gui.comboBox_experimentSelect.findText("TCSPC"))
    gui._refresh_experiment_ui()
    gui.comboBox_setupSelect.setCurrentIndex(gui.comboBox_setupSelect.findText("TXT/CSV"))
    gui._refresh_setup_ui()
    for key, value in dict(
        skiprows=11,
        reading_routine="csv",
        is_vv_vh=False,
        use_header=True,
        matrix_columns=[],
        polarization="vm",
        rep_rate=10.0,
        dt=0.0141,
    ).items():
        setattr(gui.current_setup, key, value)
    cs.macros.add_dataset(filename=DECAY)


def test_main_window_autosaves_without_asking(monkeypatch, tmp_path):
    from chisurf.core.project import storage
    from chisurf.core.project.lifecycle import Autosave
    from chisurf.startup import gui_services

    gui = cs.cs
    # Let the post-show startup services finish: the registered start_autosave
    # service must have armed the shipped default, and must not later replace
    # the one-second timer this test installs.
    runner = getattr(gui, "_bg_startup_runner", None)
    if runner is not None:
        for _ in range(600):
            if runner._index >= len(runner._specs):
                break
            QTest.qWait(100)
        assert runner._index >= len(runner._specs), "startup services did not finish"
        assert isinstance(gui._autosave, Autosave)
        assert gui._autosave_timer.interval() == int(gui._autosave.interval_s * 1000)
    settings = cs.core.settings.cs_settings
    project_settings = dict(settings.get("project") or {})
    project_settings["autosave"] = {"enabled": True, "interval_s": 1}
    monkeypatch.setitem(settings, "project", project_settings)
    monkeypatch.setattr(cs, "working_path", str(tmp_path), raising=False)
    gui._get_project_document().reset()

    gui_services.start_autosave(types.SimpleNamespace(dependencies={}, main_window=gui))
    try:
        assert gui._autosave.interval_s == 1.0
        assert gui._autosave_timer.isActive()
        _load_decay()
        assert gui._project_has_content()
        target = Autosave.target(gui._get_project_document(), tmp_path)
        QTest.qWait(3000)
        assert target.is_file(), "no autosave file after three one-second ticks"
        assert QtWidgets.QApplication.activeModalWidget() is None
        assert storage.load_file(target).datasets
        # Autosave is not a save: the session still counts as unsaved.
        assert gui._get_project_document().path is None

        # An explicit save makes the autosave copy obsolete and removes it.
        saved = tmp_path / "explicit.cs.pto"
        assert gui._save_project_snapshot(save_as=saved) is True
        assert saved.is_file()
        assert not target.exists()
        assert not Autosave.target(gui._get_project_document(), tmp_path).exists()
    finally:
        gui._autosave_timer.stop()
        gui._get_project_document().reset()
        cs.core.actions.dispatch(name="fit.close_all", payload={})
        cs.imported_datasets.clear()
