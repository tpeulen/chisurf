"""The FPS JSON Editor's Guide button starts the labelling-editor tour, not ChiMOL's general one."""

from __future__ import annotations

import pytest
from emtk.testing import Driver


def test_guide_button_starts_the_labelling_editor_tour():
    """Press the real Guide button of the opened window; chimol's ``fps_editor`` tour must run."""
    from chisurf.plugins.modelling.fps_json_editor.gui.app import make_app

    app = make_app()
    try:
        driver = Driver(app, (1100, 800))
        driver.draw(3)
        if not app._ensure_chimol():
            pytest.skip(f"chimol unavailable: {app._error}")
        driver.draw(2)
        driver.click(app.item_rects["guide"])
        driver.draw(2)
        gui = app._chimol_app.viewer.renderer._internal_gui
        assert gui.tour is not None and gui.tour.title == "Edit a labelling plan"
        assert not app.tour.active, "the general viewer tour must not start"
    finally:
        app.close()
