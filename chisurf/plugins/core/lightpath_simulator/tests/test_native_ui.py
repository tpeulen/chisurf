"""UI-level checks for the lightpath tool shell and its frame economy.

The native app's constructor must not repaint at full frame rate while idle
(the whole UI went laggy), and the Qt window must shut the controller down on
close — the executor, the state file and the registered parameters live there.
"""

from __future__ import annotations

import os

import pytest

try:
    from qtpy import QtWidgets
except ImportError:
    QtWidgets = None  # type: ignore[assignment]

_needs_qt = pytest.mark.skipif(QtWidgets is None, reason="Qt bindings not available")

_APP: list = []


def _ensure_app():
    _APP[:] = [QtWidgets.QApplication.instance() or QtWidgets.QApplication([])]


@pytest.fixture
def tool(qapp):
    _ensure_app()
    from chisurf.plugins.core.lightpath_simulator.gui.tool import (
        LightPathSimulatorWidget,
    )

    tool = LightPathSimulatorWidget()
    yield tool
    tool.close()


@_needs_qt
def test_the_tool_hosts_the_native_app(tool):
    from emtk.qt_host import host_class

    assert isinstance(tool.host, host_class())
    assert tool.light_path_app is tool.host.control
    assert tool.light_path_app.controller.client is tool.client


@_needs_qt
def test_an_idle_editor_does_not_request_continuous_frames(tool):
    """Idle: no animation. With a job in flight: frames to poll it."""
    app = tool.light_path_app
    assert app.continuous is False
    assert app.animating() is False, "the idle editor must not burn frames"

    app.controller.running = True
    assert app.animating() is True, "a running job needs polling frames"
    app.controller.running = False

    app.controller.pending = True
    assert app.animating() is True, "a queued auto-update needs polling frames"
    app.controller.pending = False
    assert app.animating() is False


@_needs_qt
def test_window_close_shuts_the_controller_down(tool, monkeypatch):
    """closeEvent reaches the controller (executor, state file, parameters)."""
    calls: list[str] = []
    monkeypatch.setattr(tool.light_path_app.controller, "close", lambda: calls.append("closed"))
    tool.close()
    assert calls == ["closed"]


@_needs_qt
def test_the_preserved_module_helpers(tool):
    """_json_safe / _deserialize_numpy survive for the headless consumers."""
    import numpy as np

    from chisurf.plugins.core.lightpath_simulator.gui.tool import (
        _deserialize_numpy,
        _json_safe,
    )

    assert _json_safe(np.array([1.0, 2.0])) == [1.0, 2.0]
    assert _json_safe({"a": np.float64(1.5), "_private": 1}) == {"a": 1.5}
    back = _deserialize_numpy({"curve": [1, 2, 3]})
    assert back["curve"].dtype == np.float64


@_needs_qt
def test_a_dropped_graph_file_loads(tool, tmp_path, monkeypatch):
    """Dropping a .json graph file replaces the editor's document."""
    graph = {
        "nodes": [
            {"id": "src", "type": "light_source", "x": 50, "y": 60},
            {"id": "det", "type": "detector", "x": 300, "y": 60},
        ],
        "edges": [],
    }
    import json as _json

    graph_file = tmp_path / "path.json"
    graph_file.write_text(_json.dumps(graph))

    loaded: list = []
    monkeypatch.setattr(
        tool.light_path_app.controller,
        "load_graph",
        lambda path: loaded.append(path),
    )
    tool.light_path_app.on_paths_dropped([str(graph_file)])
    assert loaded == [str(graph_file)]


@_needs_qt
def test_the_catalogue_auto_loads_on_the_first_frame(tool, monkeypatch):
    """The easy setup's spectrum/sample dropdowns open populated.

    The old tool loaded the MMFDB catalogue at startup; the port lost that,
    and every spectrum dropdown opened with only "None".
    """
    app = tool.light_path_app
    requests: list[str] = []
    monkeypatch.setattr(
        app.controller, "start", lambda action="simulate", **k: requests.append(action)
    )

    import emtk
    from emtk.testing import RecordingPainter

    app._easy_placed = True  # skip placement; probe the catalogue path alone
    app._catalogue_requested = False
    p = RecordingPainter()
    with emtk.frame(p, (0.0, 0.0, 1280.0, 800.0)):
        app._render()
    with emtk.frame(p, (0.0, 0.0, 1280.0, 800.0)):
        app._render()

    assert "catalogue" in requests, "the catalogue was not requested on the first frame"
    # Exactly once, however many frames render.
    assert requests.count("catalogue") == 1


@_needs_qt
def test_loaded_probes_reach_both_dropdown_sources(tool, monkeypatch):
    """on_probes feeds the easy widget AND the graph's node bodies."""
    app = tool.light_path_app
    probes = [{"probe_id": "d1", "name": "ATTO 647N", "has_qe": True}]
    app.controller.probes = probes
    app.controller.on_probes(probes)

    assert list(app.easy.probes) == probes
    assert app.content.probes == probes
