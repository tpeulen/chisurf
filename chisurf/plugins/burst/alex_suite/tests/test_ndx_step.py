"""The E-S step is ChiSurf's ndX window, and it is handed the workflow's bursts.

The step used to embed the legacy Qt ndX window, which loaded its equations in
a deferred init that could run *after* the step handed it files -- the table
then had no E and S. The emtk app has its equations from its settings when it
is built, so a table handed over always gets its derived columns.
"""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtWidgets  # noqa: E402

from chisurf.plugins.burst.alex_suite.gui.tool import AlexSuiteTool  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Workflow:
    """The two things ``_apply_context_to_es`` reads from the tool."""

    def __init__(self, files):
        self._files = files
        self._es_loaded = None
        self._refresh_ndx_parameters = AlexSuiteTool._refresh_ndx_parameters

    def _ndx_sources(self):
        return list(self._files), None


def _wait(window, timeout=30.0):
    """Let the window's background load finish (the host keeps drawing)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QtWidgets.QApplication.processEvents()
        window.host.grab()
        if window.app.model.has_data:
            return
        time.sleep(0.05)
    raise AssertionError(f"ndX did not load: {window.app.model.error!r}")


def test_the_es_step_opens_the_bursts_once(qapp, tmp_path, monkeypatch):
    """The step opens the files with the app's equations; a revisit does not reload."""
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndx"))
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    table = tmp_path / "bursts.csv"
    table.write_text("Number of Photons,Duration (ms)\n120,1.5\n80,0.9\n300,2.2\n")
    window = build_ndxplorer_window(session_autosave=False, layout_store=None)
    try:
        assert window.app.model.manager.equations, "the app has no equations to compute"
        flow = _Workflow([str(table)])
        AlexSuiteTool._apply_context_to_es(flow, window)
        _wait(window)
        assert window.app.model.source.size == 3
        assert flow._es_loaded == [str(table)]

        opened = []
        monkeypatch.setattr(window, "open_paths", lambda *a, **k: opened.append(a))
        AlexSuiteTool._apply_context_to_es(flow, window)
        assert not opened, "returning to the step re-opened the same files"
    finally:
        window.close()
