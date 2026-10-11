"""New burst control help uses the existing locale seam without changing settings."""

from __future__ import annotations

import copy

import pytest
from emtk import i18n
from emtk.testing import Driver


@pytest.fixture(autouse=True)
def isolated_preferences(tmp_path, monkeypatch):
    """Keep rendering preferences and the temporary catalog local to each test."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    monkeypatch.setattr(i18n, "_catalogs", copy.deepcopy(i18n._catalogs))
    monkeypatch.setattr(i18n, "_locale", "en")


def translated_tooltip_sink(monkeypatch, owner, sources):
    """Observe real tooltip calls while leaving the actual renderer active."""
    translations = {text: "Localized: " + text for text in sources}
    i18n.add_translations("burst-contract", translations)
    i18n.set_locale("burst-contract")
    observed = []
    original = owner.im.set_item_tooltip

    def record(text):
        """Record each submitted tooltip and continue through the real widget API."""
        observed.append(text)
        return original(text)

    monkeypatch.setattr(owner.im, "set_item_tooltip", record)
    return translations, observed


def test_bid_output_help_reaches_translated_sink_without_changing_conversion_settings(monkeypatch):
    """The real conversion panel translates its new output help before rendering."""
    from chisurf.plugins.burst.bid_to_analysis.gui import app as owner

    app = owner.BidToAnalysisApp()
    try:
        before = copy.deepcopy(app.export_settings())
        sources = (
            "Add a numeric suffix instead of reusing an existing output folder.",
            "Archive generated analysis files while keeping the output folder.",
            "Explicit output destination; empty uses the BID stem beside its TTTR measurement.",
        )
        translations, observed = translated_tooltip_sink(monkeypatch, owner, sources)
        Driver(app, (1100, 720)).draw(3)
        assert set(translations.values()) <= set(observed)
        assert not set(sources) & set(observed)
        assert app.export_settings() == before
        assert not app.running and app.future is None
    finally:
        app.close()


def test_h2mm_tuple_help_is_translated_at_actual_controls_without_changing_fit_options(monkeypatch):
    """Spec-held descriptions of the native H2MM form go through the normal translation path."""
    from chisurf.plugins.burst.burst_h2mm.gui import native as owner

    sources = (
        "Random initialisations per state count; the best log-likelihood wins.",
        "Maximum EM iterations per fit.",
        "Bursts with fewer stream photons are left out.",
    )
    names = ("restarts", "max_iter", "min_photons")
    # The settings form draws its descriptions through emtk.im_widgets.
    from types import SimpleNamespace

    from emtk import im_widgets

    translations, observed = translated_tooltip_sink(
        monkeypatch, SimpleNamespace(im=im_widgets), sources
    )
    # The spec is translated when the app loads it, so the app is built after the locale is set.
    app = owner.H2mmNativeApp()
    before = tuple(getattr(app.model, name) for name in names)
    Driver(app, (1100, 3000)).draw(3)
    assert set(translations.values()) <= set(observed)
    assert not set(sources) & set(observed)
    assert tuple(getattr(app.model, name) for name in names) == before


def test_header_editor_new_help_and_labels_translate_without_mutating_real_tags(monkeypatch):
    """Translated header actions keep their remembered targets and real tag data."""
    from types import SimpleNamespace

    from chisurf.plugins.tttr.tttr_header_edit.gui import app as owner
    from chisurf.plugins.tttr.tttr_header_edit.gui.view_model import HeaderEditorViewModel

    model = HeaderEditorViewModel()
    opened = []
    app = owner.HeaderEditorApp(
        tool=SimpleNamespace(model=model), on_open=lambda: opened.append(True)
    )
    before = copy.deepcopy(model.tags)
    sources = (
        "Open a TTTR file (PTU / HT3 / SPC / HDF5) and read its header.",
        "Append a new header tag with a placeholder name.",
        "Header tag name; names must not be empty.",
    )
    translations, observed = translated_tooltip_sink(monkeypatch, owner, sources)
    i18n.add_translations("burst-contract", {"Open…": "Localized open"})
    driver = Driver(app, (1100, 800))
    painter = driver.draw(3)
    assert set(translations.values()) <= set(observed)
    assert "📂  Localized open" in painter.strings
    driver.click("open")
    assert opened == [True]
    assert model.tags == before
