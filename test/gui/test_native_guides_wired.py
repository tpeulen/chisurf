"""Five native apps ship a Guide: a tour whose every target is drawn, with an awaited, real control.

A ``guide.json`` that no app builds, or a step whose target the app never records, is invisible to a
construction test: the Guide button is missing, or the card is shown centred and points at nothing.
"""

from __future__ import annotations

import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APPS = {
    "style_manager": "chisurf.plugins.core.style_manager.gui.app:make_style_manager_app",
    "code_editor": "chisurf.plugins.core.code_editor.gui.editor_app:make_editor_app",
    "games": "chisurf.plugins.misc.games.gui.app:make_app",
    "fret_docking": "chisurf.plugins.modelling.fret.gui.app:make_app",
}


def _owner(app):
    """The object holding the tour (the app, or the editor surface it composes)."""
    return app if getattr(app, "tour", None) is not None else app.editor_gui


@pytest.mark.parametrize("name", sorted(APPS))
def test_every_tour_target_is_drawn_and_one_step_awaits(name, tmp_path, monkeypatch):
    from emtk.testing import Driver

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    module, attr = APPS[name].split(":")
    app = getattr(importlib.import_module(module), attr)()
    try:
        tour = _owner(app).tour
        assert tour.steps and any(step.get("await") for step in tour.steps)
        assert tour.wait_for_controls
        driver = Driver(app, (1200, 800))
        driver.draw(3)
        if name == "code_editor":
            app.model.new_document()  # the text area is only drawn once a document exists
            driver.draw(3)
        missing = []
        for index, step in enumerate(tour.steps):
            key = tour._target_key(step.get("target"))
            if key and tour.get_target_rect(key) is None:
                missing.append((index, key))
        assert not missing, f"{name}: tour targets never drawn: {missing}"
    finally:
        close = getattr(app, "close", None)
        if callable(close):
            close()
