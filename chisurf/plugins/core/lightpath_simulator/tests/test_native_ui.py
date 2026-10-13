"""UI-level checks for the light-path window and its frame economy.

The window is the emtk app; both shells open it from the manifest's ``emtk`` entry (the ``--qt`` shell hosts
it in a ``ControlHost``), so there is no Qt tool of its own any more. The app must not repaint at full frame
rate while idle (the whole UI went laggy), and closing it must shut the controller down -- the executor, the
state file and the registered parameters live there. Formerly these ran on the Qt host window.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

PLUGIN = Path(__file__).resolve().parents[1]


def test_the_manifest_opens_the_native_app_and_names_no_qt_window(app):
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    assert "gui" not in manifest["entrypoints"], "the shells host the emtk app; there is no Qt tool"
    module, factory = manifest["entrypoints"]["emtk"].split(":")
    import importlib

    from chisurf.plugins.core.lightpath_simulator.gui.app import LightPathApp

    assert getattr(importlib.import_module(module), factory) is not None
    assert isinstance(app, LightPathApp)
    assert app.controller.client is not None and app.controller.remote


def test_an_idle_editor_does_not_request_continuous_frames(app):
    """Idle: no animation. With a job in flight: frames to poll it."""
    assert app.continuous is False
    assert app.animating() is False, "the idle editor must not burn frames"

    app.controller.running = True
    assert app.animating() is True, "a running job needs polling frames"
    app.controller.running = False

    app.controller.pending = True
    assert app.animating() is True, "a queued auto-update needs polling frames"
    app.controller.pending = False
    assert app.animating() is False


def test_window_close_shuts_the_controller_down(app, monkeypatch):
    """Closing the window reaches the controller (executor, state file, parameters)."""
    calls: list[str] = []
    real = app.controller.close
    monkeypatch.setattr(app.controller, "close", lambda: (calls.append("closed"), real()))
    app.close()
    assert calls == ["closed"]


def test_the_module_helpers_for_the_headless_consumers():
    """The JSON helpers the Qt tool kept (``_json_safe`` / ``_deserialize_numpy``) are the controller's."""
    from chisurf.plugins.core.lightpath_simulator.gui.controller import deserialize, json_safe

    assert json_safe(np.array([1.0, 2.0])) == [1.0, 2.0]
    assert json_safe({"a": np.float64(1.5), "_private": 1}) == {"a": 1.5}
    back = deserialize({"curve": [1, 2, 3]})
    assert back["curve"].dtype == np.float64


def test_a_dropped_graph_file_loads(app, tmp_path, monkeypatch):
    """Dropping a .json graph file replaces the editor's document."""
    graph = {
        "nodes": [
            {"id": "src", "type": "light_source", "x": 50, "y": 60},
            {"id": "det", "type": "detector", "x": 300, "y": 60},
        ],
        "edges": [],
    }
    graph_file = tmp_path / "path.json"
    graph_file.write_text(json.dumps(graph))

    loaded: list = []
    monkeypatch.setattr(app.controller, "load_graph", lambda path: loaded.append(path))
    assert app.on_paths_dropped([str(graph_file)])
    assert loaded == [str(graph_file)]


def test_the_catalogue_auto_loads_on_the_first_frame(app, monkeypatch):
    """The easy setup's spectrum/sample dropdowns open populated.

    The old tool loaded the MMFDB catalogue at startup; the port lost that,
    and every spectrum dropdown opened with only "None".
    """
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


def test_loaded_probes_reach_both_dropdown_sources(app):
    """on_probes feeds the easy widget AND the graph's node bodies."""
    probes = [{"probe_id": "d1", "name": "ATTO 647N", "has_qe": True}]
    app.controller.probes = probes
    app.controller.on_probes(probes)

    assert list(app.easy.probes) == probes
    assert app.content.probes == probes


def test_the_window_settings_carry_the_graph_the_qt_host_saved_on_close(app):
    """The Qt host wrote the graph to QSettings on close; the shells persist ``export_settings`` instead."""
    settings = app.export_settings()
    assert [n["type"] for n in settings["graph"]["nodes"]] == [
        n.type for n in app.controller.document.nodes
    ]
    app.controller.add_node("detector", (5.0, 5.0))
    n = len(app.controller.document.nodes)
    app.restore_settings(settings)
    assert len(app.controller.document.nodes) == n - 1
