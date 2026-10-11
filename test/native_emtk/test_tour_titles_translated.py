"""A tour card draws its step title in the session language, whichever catalogue holds it."""

from __future__ import annotations

import pytest

from chisurf.emtk.i18n import set_locale
from chisurf.emtk.plugins import load_plugin


@pytest.mark.parametrize(
    ("locale", "expected"),
    [("fr", "Charger un fichier VV/VH"), ("de", "VV/VH-Datei laden")],
)
def test_tour_card_title_is_translated(locale, expected):
    from emtk.testing import Driver

    app = load_plugin("vv_vh_anisotropy", persist=False)
    try:
        set_locale(locale)
        driver = Driver(app, (1100, 720))
        driver.settle()
        app.tour.start(0)
        driver.frame(3)
        drawn = " | ".join(t[5] for t in driver.painter.texts)
        assert expected in drawn, drawn[:600]
    finally:
        set_locale("en")
        app.close()
