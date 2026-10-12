"""Confirmed click-all callbacks use the public native event contracts."""

from types import SimpleNamespace

from emtk import im
from emtk.app import ImApp
from emtk.testing import Driver
from emtk.view_form import FormState, draw_form


def test_global_refresh_toggle_accepts_the_value_delivered_by_a_form():
    """Changing a declared toggle rebuilds a stale graph exactly once."""
    from chisurf.plugins.core.globalview.gui.model import GlobalViewModel

    model = GlobalViewModel.__new__(GlobalViewModel)
    model.auto_refresh = False
    model.stale = True
    calls = []
    model.rebuild = lambda **kwargs: calls.append(kwargs)
    model._update_status = lambda: None
    state = FormState()
    spec = {
        "sections": [
            {
                "type": "toggle",
                "attr": "auto_refresh",
                "call": "auto_refresh_changed",
                "description": "Refresh changed fits.",
            }
        ]
    }
    app = ImApp(lambda: draw_form(spec, model, state))
    app.form = state
    driver = Driver(app, (360, 200))
    driver.frame(2)
    driver.click("auto_refresh")
    assert model.auto_refresh is True
    assert calls == [{"force": True}]
    model.auto_refresh_changed()  # Existing direct model callers remain valid.


def test_hub_key_release_supports_optional_child_event_hooks():
    """A valid draw/key child need not implement every host event hook."""
    from chisurf.plugins.modelling.fret.gui.app import FretApp

    app = FretApp.__new__(FretApp)
    app.selected = "Test"
    app.children = {"Test": SimpleNamespace(key=lambda *args: True)}
    assert app.key_release(1) is False
    calls = []
    app.child.key_release = lambda *args: calls.append(args) or True
    assert app.key_release(2, "", 3)
    assert calls == [(2, "", 3)]


def test_pto_picker_is_drawn_through_its_actual_render_contract():
    """Opening the database picker reaches its renderer without a fake alias."""
    from chisurf.plugins.core.pto_inspector.gui.app import make_app

    app = make_app()
    calls = []
    app.picker = SimpleNamespace(render=lambda frame: calls.append(frame))
    try:
        Driver(app, (900, 640)).frame(2)
        assert calls == [(0.0, 0.0, 900.0, 640.0)] * 2
    finally:
        app.picker = None
        app.close()
