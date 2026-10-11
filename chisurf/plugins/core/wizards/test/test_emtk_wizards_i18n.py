"""The Wizards hub speaks the chosen language everywhere it draws, and its rail fits the translated buttons."""

from __future__ import annotations

import pytest

from chisurf.plugins.core.project_browser.test.driving import clipped_texts, draw_clip
from chisurf.plugins.emtk_hermetic import hermetic, real_chisurf_untouched  # noqa: F401
from chisurf.plugins.emtk_test_input import Driver

from ..core.registry import default_wizards
from ..gui.app import WizardHubApp

SIZES = [(1100, 720), (800, 600)]


@pytest.fixture
def language():
    """Switch the toolkit to a language for one test and back to English afterwards."""
    from chisurf.emtk import i18n

    i18n.install("en")

    def choose(code):
        i18n.set_locale(code)

    yield choose
    i18n.set_locale("en")


@pytest.mark.parametrize("code", ["de", "fr"])
def test_catalogue_text_is_translated_in_the_list_and_the_header(language, code):
    from emtk.i18n import tr

    language(code)
    app = WizardHubApp()
    d = Driver(app, (1100, 720))
    for entry in default_wizards():
        for text in (entry.label, entry.description):
            assert tr(text) != text, f"{text!r} has no {code} translation"
        d.click_name("entry:" + entry.id)
        strings = d.draw(3).strings
        assert tr(entry.label) in strings and tr(entry.description) in strings
        assert entry.description not in strings
    assert "Batch analysis" not in d.draw(2).strings
    app.close()


@pytest.mark.parametrize("code", ["de", "fr"])
def test_hosted_wizard_docks_and_steps_are_translated(language, code):
    from emtk.i18n import tr

    language(code)
    app = WizardHubApp()
    Driver(app, (1100, 720)).draw(3)
    strings = Driver(app, (1100, 720)).draw(3).strings
    for text in ("Anisotropy workflow", "Workflow step"):
        assert tr(text) != text and tr(text) in strings and text not in strings
    app.select("batch_analysis")
    strings = Driver(app, (1100, 720)).draw(3).strings
    for text in ("Batch Analysis", "Steps"):
        assert text not in strings or tr(text) == text
    assert "Before you start:" not in strings and tr("Before you start:") != "Before you start:"
    app.close()


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("code", ["en", "de", "fr"])
def test_the_rail_holds_its_guide_and_help_buttons(language, code, size):
    """The two captions are measured in the active language: neither runs past the rail."""
    language(code)
    app = WizardHubApp()
    painter = draw_clip(app, size)
    rail = app.child_box[0]
    for key in ("guide", "help"):
        x, _y, w, _h = app.item_rects[key]
        assert x + w <= rail + 0.5, (code, size, key, x + w, rail)
    # The hosted wizard's own dock tab ("Anisotropy workflow" / its translation) is the child's layout, not the rail's.
    from emtk.i18n import tr

    own = f"'{tr('Anisotropy workflow')}'"
    assert [c for c in clipped_texts(painter) if own not in c] == []
    app.close()
