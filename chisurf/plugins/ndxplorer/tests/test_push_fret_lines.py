"""The FRET-line tool's *Push to ndX* draws its lines in every open ndX window.

The lines arrive as data curves of ndX's Overlays tab (E vs tau_F), through
:func:`chisurf.plugins.ndxplorer.window.push_overlay_lines` and the app's
``add_overlay_lines``. ``NDX_PUSH_SHOT=<png>`` saves the window with the lines.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtWidgets  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(autouse=True)
def _scratch_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndxplorer"))


def _two_lines():
    from chisurf.plugins.fret_line.gui.model import FretLineModel

    model = FretLineModel()
    model.minimum, model.maximum = 20.0, 120.0
    model.add_line()
    model.tau_d0 = 3.0  # a second donor: a second line
    model.add_line()
    return model


def _bursts(line):
    """Bursts scattered about a FRET line, as a table with tau and E columns."""
    from ndxplorer.core.data_source import DataSource

    rng = np.random.default_rng(7)
    r = line["result"]
    i = rng.integers(0, len(r["tau_f"]), 3000)
    tau = np.asarray(r["tau_f"])[i] + rng.normal(0, 0.15, i.size)
    e = np.asarray(r["e_fret"])[i] + rng.normal(0, 0.04, i.size)
    return DataSource.from_columns({"tau_f (ns)": tau, "E": e})


def test_push_draws_the_lines_in_an_open_window_and_none_after_it_closes(qapp):
    from chisurf.plugins.fret_line.gui.model import push_to_ndx
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    tool = _two_lines()
    window = build_ndxplorer_window(session_autosave=False, layout_store=None)
    try:
        window.show_source(_bursts(tool.lines[0]))
        app = window.app
        app.model.set_parameter("x", "tau_f (ns)")
        app.model.set_parameter("y", "E")
        tool.push_callback = push_to_ndx
        tool.push()
        assert tool.message == "Sent 2 line(s) to ndX" and not tool.dialog_text
        overlays = next(f for f in app.features if f.name == "overlays")
        curves = overlays.overlays.curves
        assert [c.title for c in curves] == ["FRET line — Line 1 · " + tool.lines[0]["sweep_label"],
                                             "FRET line — Line 2 · " + tool.lines[1]["sweep_label"]]
        assert [c.kind for c in curves] == ["data", "data"]
        assert curves[0].color == tool.lines[0]["color"]
        np.testing.assert_allclose(curves[0].function()[1], tool.lines[0]["result"]["e_fret"])
        assert overlays.session_state()["curves"][0]["kind"] == "data"
        # pushing again updates, not duplicates
        tool.push()
        assert len(overlays.overlays.curves) == 2
        try:
            app.docks.focus("Overlays")
        except Exception:  # noqa: BLE001 - only the screenshot's tab
            pass
        window.resize(1400, 900)
        window.show()
        qapp.processEvents()
        shot = os.environ.get("NDX_PUSH_SHOT")
        if shot:
            window.grab().save(shot)
    finally:
        window.close()
    tool.dialog_ok()
    assert window.app._closed
    from ndxplorer.app.frame import live_apps

    if not live_apps():
        tool.push()
        assert tool.dialog_text.startswith("No ndX window is open")
    tool.close()


def test_an_open_window_with_incompatible_axes_reports_rejection_not_absence(qapp):
    from ndxplorer.core.data_source import DataSource

    from chisurf.plugins.fret_line.gui.model import push_to_ndx
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    tool = _two_lines()
    window = build_ndxplorer_window(
        data_source=DataSource.from_columns({"x": [1., 2.], "y": [3., 4.]}),
        session_autosave=False, layout_store=None,
    )
    try:
        tool.push_callback = push_to_ndx

        tool.push()

        assert "rejected the lines" in tool.dialog_text, tool.dialog_text
        assert "No ndX window is open" not in tool.dialog_text
    finally:
        window.close()
        tool.close()
