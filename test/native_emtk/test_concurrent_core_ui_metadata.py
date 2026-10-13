"""New acquisition/About controls retain behavior while exposing translated help."""

import copy
from pathlib import Path

import pytest
from emtk.testing import Driver

from build_tools.dev_utils.ui_contract_audit import audit_python, audit_translation_python

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("plugin", ["acq", "about"])
def test_owned_source_has_no_direct_tooltip_or_literal_omissions(plugin):
    """The two bounded new-control files carry their complete direct UI contract."""
    path = ROOT / "chisurf/plugins/core" / plugin / "gui/app.py"
    source = path.read_text()
    assert audit_python(source, str(path.relative_to(ROOT))) == []
    assert audit_translation_python(source, str(path.relative_to(ROOT))) == []


def test_acquisition_real_bh_hover_translates_help_without_device_writes(monkeypatch, tmp_path):
    """Real setup fields expose specific help while backend writes remain explicit."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    from chisurf.plugins.core.acq.gui import app as module
    from chisurf.plugins.core.acq.test.test_emtk_acq_native import FakeBHSetupAdapter

    translated = "Détecter les modules BH avec le mode de simulation sélectionné."
    source = "Discover BH modules through the supplied adapter using the selected simulation mode."
    catalog = {"Detect Cards": "Détecter", "Apply": "Appliquer", source: translated}
    import emtk.im_widgets
    import emtk.view_form

    # the card is its view.json: the form translates its labels, the widgets its tooltips
    fake_tr = lambda text, *a, **k: catalog.get(text, text)  # noqa: E731
    monkeypatch.setattr(emtk.view_form, "tr", fake_tr)
    monkeypatch.setattr(emtk.im_widgets, "tr", fake_tr)
    device = FakeBHSetupAdapter()
    model = module.AcquisitionNativeModel(device_factory=lambda _kind: device)
    model.device_type = "BH_SPC"
    model.device = device
    app = module.AcquisitionApp(model)
    app.io.wall_clock = False
    try:
        app._open_device_setup()
        driver = Driver(app, (1200, 800))
        painter = driver.frame(2)
        assert "Détecter" in painter.strings and "Appliquer" in painter.strings
        original = copy.deepcopy(app.setup_model.values)
        calls = list(device.calls)
        driver.hover(app.item_rects["setup_detect_cards"])
        app.io.now += 1.0
        painter = driver.frame(2)
        assert translated in " ".join(painter.strings)
        assert app.setup_model.values == original and device.calls == calls
        driver.click(app.item_rects["setup_detect_cards"])
        assert device.calls[-1] == ("detect_cards", False)
        driver.hover(app.item_rects["setup_CFD_LIMIT_LOW"])
        app.io.now += 1.0
        painter = driver.frame(2)
        assert "-1000 to 1000" in " ".join(painter.strings)
        assert not any(call[0] == "set_parameter" for call in device.calls)
    finally:
        app.close()


def test_about_uses_translated_identity_and_real_close_action(monkeypatch):
    """Localized display text and tooltip preserve the existing close request."""
    from chisurf.plugins.core.about.gui import app as module

    translations = {
        "ChiSurf": "ChiSurf localisé",
        "Close": "Fermer",
        "Close the About ChiSurf window.": "Fermer la fenêtre À propos de ChiSurf.",
    }
    monkeypatch.setattr(module, "tr", lambda text: translations.get(text, text))
    app = module.AboutApp()
    app.io.wall_clock = False
    driver = Driver(app, app.window_size)
    painter = driver.frame(2)
    assert "ChiSurf localisé" in painter.strings and "✕  Fermer" in painter.strings
    assert not app.close_requested
    driver.hover("close_about")
    app.io.now += 1.0
    painter = driver.frame(2)
    assert translations["Close the About ChiSurf window."] in " ".join(painter.strings)
    driver.click("close_about")
    assert app.close_requested
