"""Spectra endpoint options explain their destinations through translated hover help."""

import json

from build_tools.dev_utils.ui_contract_audit import audit_json
from chisurf.plugins.spectra_downloader.gui import app as owner


def test_endpoint_declaration_has_no_missing_help():
    """Each visible endpoint control and radio option carries nonempty help."""
    path = owner.HERE / "endpoint_auth.view.json"
    assert audit_json(path.read_text(), str(path)) == []


def test_radio_option_help_uses_the_existing_translation_adapter(monkeypatch):
    """Labels and individual descriptions follow the same locale translation path."""
    spec = json.loads((owner.HERE / "endpoint_auth.view.json").read_text())
    monkeypatch.setattr(owner, "tr", lambda text: "translated: " + text)
    result = owner.translated(spec)
    choice = result["sections"][0]
    assert len(choice["descriptions"]) == len(choice["options"]) == 2
    assert all(text.startswith("translated: ") for text in choice["descriptions"])
    assert spec["sections"][0]["options"] == ["local", "server"]


def test_each_radio_delivers_its_specific_help_to_the_renderer(monkeypatch):
    """The existing form renderer attaches each note to its own radio target."""
    from types import SimpleNamespace

    from emtk import im_widgets
    from emtk.app import ImApp
    from emtk.testing import Driver
    from emtk.view_form import FormState, draw_form

    spec = json.loads((owner.HERE / "endpoint_auth.view.json").read_text())
    choice = owner.translated(spec)["sections"][0]
    state = FormState()
    model = SimpleNamespace(mode="local")
    received = []
    original = im_widgets.set_item_tooltip

    def record(text):
        """Observe the production tooltip call while preserving its behavior."""
        received.append(text)
        return original(text)

    monkeypatch.setattr(im_widgets, "set_item_tooltip", record)
    app = ImApp(lambda: draw_form({"sections": [choice]}, model, state))
    app.form = state
    driver = Driver(app, (700, 220))
    driver.draw(3)
    for target in ["mode.0", "mode.1"]:
        driver.hover(target)
        driver.draw(2)
    assert set(choice["descriptions"]) <= set(received)
    assert state.rects["mode.0"] != state.rects["mode.1"]
    assert model.mode == "local"
