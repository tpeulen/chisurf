"""Existing host captions expose authored help without changing their content."""

from __future__ import annotations

import copy

import numpy as np
import pytest
from emtk import i18n
from emtk.i18n.testing import isolated
from emtk.testing import Driver


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Keep application preferences, metadata and translation changes local."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    with isolated(language="en"):
        yield


def populated_app(kind, tmp_path):
    """Construct the real host and load its existing deterministic photon fixture."""
    if kind == "ai":
        from chisurf.plugins.ai_settings.gui.app import AISettingsApp

        return AISettingsApp()

    from chisurf.plugins.microscopy.imaging_emtk import pixel_testing as data

    path = data.flim_ptu(tmp_path / "flim.ptu")
    if kind == "photons":
        from chisurf.plugins.tttr.photon_table.gui.app import PhotonTableApp

        app = PhotonTableApp()
        assert app.model.load_path(str(path))
        assert app.model.rows
        return app

    from chisurf.plugins.microscopy.imaging_emtk import pixel_checks
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver as ImagingDriver
    from chisurf.plugins.microscopy.img_pixel_intensity.gui.app import IntensityApp

    app = IntensityApp()
    model = pixel_checks.computed(app, ImagingDriver(app, (1200, 800)), path)
    np.testing.assert_array_equal(model.intensity_map(), data.counts(1)[0].sum(axis=0))
    return app


def results(app, kind):
    """Snapshot real model outputs, independently of tooltip and paint state."""
    if kind == "intensity":
        return tuple(
            np.asarray(getattr(app.model, name)()).copy()
            for name in ("intensity_map", "count_rate_map", "frame_stack")
        )
    if kind == "photons":
        return copy.deepcopy((app.model.rows, app.model.export_settings()))
    return tuple(
        getattr(app.model, name)
        for name in ("provider", "base_url", "text_model", "image_model", "temperature", "top_p")
    )


def caption(app, key, floating):
    """Locate the actual dock tab or floating title, excluding header buttons."""
    if not floating:
        return app.docks.tab_rect(key)
    x, y, width, _ = app.docks.window(key).frame
    return x + width / 2, y + app.docks._title_h / 2


def geometry(driver, app):
    """Record unhovered text positions and every currently drawn control."""
    driver.hover((-20, -20))
    driver.app.io.now += 2.0
    painter = driver.draw(3)
    return list(painter.texts), dict(app.form.rects), dict(app.item_rects)


@pytest.mark.parametrize("kind", ["intensity", "ai", "photons"])
@pytest.mark.parametrize("size", [(1100, 720), (800, 600)])
def test_existing_host_header_help_paints_and_preserves_content(kind, size, tmp_path):
    """Docked and floating captions translate delayed help without moving controls."""
    app = populated_app(kind, tmp_path)
    try:
        app.io.wall_clock = False
        driver = Driver(app, size)
        panels = app.windows if kind == "intensity" else app.panels
        descriptions = {key: str(panel.get("description", "")) for key, panel in panels.items()}
        assert any(descriptions.values())
        for key, description in descriptions.items():
            assert app.docks.window(key).tooltip == description
        scientific_before = results(app, kind)
        for key, description in descriptions.items():
            if not description:
                continue
            for floating in (False, True):
                if floating:
                    app.docks.undock(key, box=(30, 30, min(size[0] - 60, 600), size[1] - 60))
                else:
                    app.docks.focus(key)
                i18n.set_locale("en")
                window = app.docks.window(key)
                window.tooltip = ""
                before = geometry(driver, app)
                window.tooltip = description
                assert geometry(driver, app) == before
                for translated in (False, True):
                    expected = f"Translated help: {description}" if translated else description
                    i18n.add_translations("test-header", {description: expected})
                    i18n.set_locale("test-header" if translated else "en")
                    driver.hover((-20, -20))
                    app.io.now += 2.0
                    driver.draw(2)
                    painter = driver.hover(caption(app, key, floating))
                    assert expected not in " ".join(painter.strings)
                    app.io.now += 1.0
                    painter = driver.draw(2)
                    assert expected in " ".join(painter.strings)
                    painter = driver.hover((-20, -20))
                    assert expected not in " ".join(painter.strings)
                if floating:
                    # Restore its region before testing another authored caption.
                    dock = str(panels[key].get("dock", "views")) if kind == "intensity" else key
                    app.docks.dock(key, dock)
        after = results(app, kind)
        if kind == "intensity":
            for expected, actual in zip(scientific_before, after, strict=True):
                np.testing.assert_array_equal(actual, expected)
        else:
            assert after == scientific_before
    finally:
        app.close()
