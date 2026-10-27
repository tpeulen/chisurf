"""New About controls retain behavior while exposing translated help."""

from pathlib import Path

import pytest
from emtk.testing import Driver

from build_tools.dev_utils.ui_contract_audit import audit_python, audit_translation_python

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("plugin", ["about"])
def test_owned_source_has_no_direct_tooltip_or_literal_omissions(plugin):
    """The bounded new-control file carries their complete direct UI contract."""
    path = ROOT / "chisurf/plugins/core" / plugin / "gui/app.py"
    source = path.read_text()
    assert audit_python(source, str(path.relative_to(ROOT))) == []
    assert audit_translation_python(source, str(path.relative_to(ROOT))) == []


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
