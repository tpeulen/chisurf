"""The native Global View app: the host services its :class:`GlobalViewSurface` needs.

The app answers the model's requests in emtk -- file dialogs, warnings, help, the guided tour,
the refresh on fit events, the layout file. The session is ``test_model._session(3)``: three
fits of ``c + a x²`` whose ``a`` follows the first fit's, so 3 owners, 6 parameters, 2 links.
"""

from __future__ import annotations

import csv
import importlib.util
import json
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


# 1. the planted session's network summary and parameter table; every request is answered
def test_the_network_of_the_planted_session():
    app, _fits, _mutator = _app()
    # three fits with two parameters each; the a of fits 2 and 3 follows fit 1's
    assert app.model.status == (
        "3 owners · 6 parameters · 2 linked. Drag a parameter onto the one it should follow."
    )
    assert len(app.model.parameter_records()) == 6
    hooks = ("ask_open_path", "ask_save_path", "warn", "open_help", "open_guide")
    assert all(getattr(app.model, k) is not None for k in hooks)


# 2. the actions answered in the app
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
    assert "OK" not in painter.strings  # the text stays in the status line


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


# 5. a fit changing elsewhere refreshes the network (the fit-event subscription)
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


# 8. persistence: the dock layout file
def test_layout_is_kept_in_globalview_layout_json(tmp_path, monkeypatch):
    import chisurf.core.settings as settings

    monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path, raising=False)
    store = gvapp._layout_store()
    assert store is not None and Path(store.path) == tmp_path / "globalview_layout.json"
    app, _fits, _mutator = _app()
    assert app.export_settings() == {}
    app.restore_settings({"x": 1})
    assert app.export_settings() == {}
