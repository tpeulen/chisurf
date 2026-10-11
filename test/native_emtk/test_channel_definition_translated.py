"""The shared detector-setup editor draws every caption translated and sizes buttons to the translation.

Found by the real-use language matrix (``tttr_image_browser``, ``lang_de`` / ``lang_fr``): table button
cells (*Delete*, *Calc G*) and the section headers were drawn from untranslated values, many captions
were in no catalogue, and a fixed 62 px button column clipped *Supprimer*.
"""

from __future__ import annotations

import pytest
from emtk.i18n.testing import isolated
from emtk.testing import RecordingPainter

from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.plugins.core.setup_channel_definition.gui.app import create_app

EXPECTED = {
    "de": {"Löschen", "G berechnen", "PIE-Fenster", "TTTR-Leseroutine", "Mikrozeit-Bereiche"},
    "fr": {"Supprimer", "Calc. G", "Fenêtres PIE", "Routine de lecture TTTR", "Plages de micro-temps"},
}
# the English *Delete* / *Calc G* the table draws under its opaque button cells are not visible, so not listed
ENGLISH = {"PIE Windows", "TTTR Reading routine", "Micro Time Ranges"}


@pytest.mark.parametrize("language", ["de", "fr"])
def test_table_buttons_and_sections_are_translated_and_not_clipped(language, tmp_path):
    from chisurf.core.support.i18n import register_catalogues

    with isolated(language=None):
        register_catalogues().set_language(language)
        app = create_app(model=ChannelDefinition(file_path=tmp_path / "setups.json"))
        try:
            app.io.wall_clock = False
            app.page.add_detector()
            app.page.add_window()
            app.page.open_sections["windows"] = True
            app.page.reset_views()
            painter = RecordingPainter()
            for _ in range(3):
                painter = RecordingPainter()
                app.draw(painter, 0.0, 0.0, 800.0, 600.0)
            # a section header is drawn behind its fold triangle
            shown = {text.strip().lstrip("▼▶").strip() for text in painter.strings}
            missing = EXPECTED[language] - shown
            assert not missing, (missing, sorted(shown))
            assert not ENGLISH & shown, ENGLISH & shown
            # every drawn button caption lies inside the 800 px frame: none is pushed off the edge
            for x, _y, w, _h, _align, text, *_ in painter.texts:
                if text.strip() in EXPECTED[language]:
                    assert x + w <= 800.0 + 1.0, (text, x, w)
        finally:
            app.close()
