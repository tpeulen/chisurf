"""The native Global View app: the host services the Qt GraphWizard gave its surface.

``GraphWizard`` and this app draw the same :class:`GlobalViewSurface`; what the
app must replace is what the Qt window answered for the model -- file dialogs,
warnings, help, the guided tour, the refresh on fit events, the layout file.
The Qt facts come from ``GraphWizard`` built in a subprocess (this process
stays Qt-free).
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("emtk")
from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.plugins.core.globalview.gui import app as gvapp  # noqa: E402

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())


def _suite():
    spec = importlib.util.spec_from_file_location("_gv_test_model", HERE / "test_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _app(size=(1200, 800)):
    model, fits, mutator = _suite()._session(3)
    app = gvapp.make_app(model=model, remember_layout=False)
    _draw(app, size)
    return app, fits, mutator


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


_QT_FACTS = r"""
import importlib.util, json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
spec = importlib.util.spec_from_file_location("_gv_test_model", sys.argv[1])
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
model, fits, mutator = t._session(3)
from chisurf.plugins.core.globalview.gui.tool import GraphWizard
w = GraphWizard(fit_list=fits, remember_layout=False)
w.resize(1200, 800)
m = w.model
print("FACTS" + json.dumps({
    "status": m.status,
    "records": len(m.parameter_records()),
    "hooks": sorted(k for k in ("ask_open_path", "ask_save_path", "warn", "open_help", "open_guide")
                    if getattr(m, k) is not None),
}))
"""


@pytest.fixture(scope="module")
def qt_facts():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT_FACTS, str(HERE / "test_model.py")],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"GraphWizard could not be built here: {proc.stderr[-800:]}")
    return json.loads(line[len("FACTS") :])


# 1. the same fits give the same network summary and parameter table as the Qt window
def test_same_network_as_the_qt_window(qt_facts):
    app, _fits, _mutator = _app()
    assert app.model.status == qt_facts["status"]
    assert len(app.model.parameter_records()) == qt_facts["records"]
    # every request the Qt window answered for the model is answered here too
    hooks = sorted(
        k
        for k in ("ask_open_path", "ask_save_path", "warn", "open_help", "open_guide")
        if getattr(app.model, k) is not None
    )
    assert hooks == qt_facts["hooks"]


# 2. the actions that needed the Qt host
def test_export_runs_through_the_in_app_file_dialog(tmp_path):
    app, _fits, _mutator = _app()
    app.model.export_parameters()
    assert app.dialog is not None and app.dialog.mode == "save"
    target = tmp_path / "params.csv"
    app.answer_file(str(target))
    assert app.dialog is None
    rows = list(csv.DictReader(target.open()))
    assert len(rows) == len(app.model.parameter_records())
    assert "Exported" in app.model.status


def test_save_and_load_network_round_trip(tmp_path):
    app, fits, _mutator = _app()
    app.model.save_network()
    target = tmp_path / "net.gml"
    app.answer_file(str(target))
    assert target.is_file() and "Saved network" in app.model.status
    fits[1].model.parameters_all_dict["c"].value = 7.0
    app.model.load_network()
    assert app.dialog is not None and app.dialog.mode == "open"
    app.answer_file(str(target))
    assert fits[1].model.parameters_all_dict["c"].value == pytest.approx(1.0)


def test_a_cancelled_dialog_changes_nothing(tmp_path):
    app, _fits, _mutator = _app()
    app.model.export_parameters()
    app.answer_file("")
    assert app.dialog is None and not list(tmp_path.iterdir())


def test_a_warning_is_an_in_app_message(tmp_path):
    app, _fits, _mutator = _app()
    app.model._warn("Cannot link", "The link was refused.")
    painter = _draw(app)
    assert "The link was refused." in painter.strings
    assert app.message_window.open and "OK" in painter.strings
    app.message_window.hide()
    painter = _draw(app)
    assert "OK" not in painter.strings  # the text stays in the status line, as in Qt


def test_help_and_guide(tmp_path):
    app, _fits, _mutator = _app()
    app.model.show_help()
    assert app.help_window.open
    app.help_window.hide()
    app.model.show_guide()
    assert app.tour.active


def test_every_guide_target_is_found_on_the_surface():
    app, _fits, _mutator = _app()
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))
    for step in steps:
        key = app.tour._target_key(step.get("target"))
        if not key:
            continue
        app.reveal(key)
        _draw(app)
        assert app.rect_of(key) is not None, key


def test_the_tour_waits_for_the_awaited_control():
    app, _fits, _mutator = _app()
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))
    index = next(i for i, s in enumerate(steps) if s.get("await"))
    app.tour.start(index)
    assert app.tour.awaiting
    name = app.tour._target_key(steps[index]["target"])
    app.forms["View"].on_used(name)
    assert not app.tour.awaiting


# 3. spec and model agree
def test_every_spec_key_exists_on_the_model():
    app, _fits, _mutator = _app()
    spec = json.loads((GUI / "globalview.view.json").read_text(encoding="utf-8"))

    def walk(sections):
        for s in sections:
            if s.get("attr"):
                assert hasattr(app.model, s["attr"]), s["attr"]
            for b in s.get("buttons", []):
                assert callable(getattr(app.model, b["action"])), b["action"]
            options = s.get("options")
            source = options.get("source") if isinstance(options, dict) else None
            if source:
                assert hasattr(app.model, source), source
            walk(s.get("sections", []))

    walk(spec["sections"])


# 4. draws populated at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_populated(size):
    app, _fits, _mutator = _app(size)
    painter = _draw(app, size)
    assert any("3 owners" in s for s in painter.strings)
    assert {"fit", "free parameter", "linked parameter"} <= set(painter.strings)


# 5. a fit changing elsewhere refreshes the network (the Qt window's fit-event subscription)
def test_fit_events_refresh_the_network(monkeypatch):
    subscribed = {}

    class _Client:
        def subscribe(self, topic, callback):
            subscribed[topic] = callback

        def unsubscribe(self, topic, callback):
            subscribed.pop(topic, None)

    fake = types.ModuleType(gvapp._FITTING_CLIENT_MODULE)
    fake.get_fitting_client = lambda: _Client()
    monkeypatch.setitem(sys.modules, gvapp._FITTING_CLIENT_MODULE, fake)
    app, fits, _mutator = _app()
    assert set(subscribed) == {"fit.", "parameter."}
    calls = []
    monkeypatch.setattr(app.model, "fits_changed", lambda: calls.append(1))
    subscribed["parameter."]("parameter.changed", {})
    assert calls == []  # only a flag on the event's thread
    _draw(app, times=1)
    assert calls == [1]
    app.close()
    assert subscribed == {}


# 6. no Qt
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("globalview")
    assert result["ok"], result["output"]


# 7. tooltips
def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("globalview"))
    assert inv["controls_without_tooltip"] == []
    spec = json.loads((GUI / "globalview.view.json").read_text(encoding="utf-8"))

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "choice", "toggle", "custom"):
                assert s.get("description"), s.get("attr") or s.get("title") or s
            options = s.get("options")
            for c in options.get("columns", []) if isinstance(options, dict) else []:
                assert c.get("description") or c.get("tooltip"), c
            for b in s.get("buttons", []):
                assert b.get("description"), b
            walk(s.get("sections", []))

    walk(spec["sections"])


# 8. persistence: the dock layout file the Qt window used
def test_layout_is_kept_where_the_qt_window_keeps_it(tmp_path, monkeypatch):
    import chisurf.core.settings as settings

    monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path, raising=False)
    store = gvapp._layout_store()
    assert store is not None and Path(store.path) == tmp_path / "globalview_layout.json"
    app, _fits, _mutator = _app()
    assert app.export_settings() == {}
    app.restore_settings({"x": 1})
    assert app.export_settings() == {}
