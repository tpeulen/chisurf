"""Settings > Styles > Blur behind dialogs: on by default, kept for the next start.

Every modal window (emtk's DialogWindow: help, questions, file and form dialogs) washes and
blurs what is behind it when the setting is on (emtk.backdrop); this is the user's switch.
"""

from __future__ import annotations

import pytest
import yaml
from emtk import backdrop
from emtk.app import ImApp

from chisurf.emtk.main_app import EmtkShellApp


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = backdrop.modal_blur()
    yield tmp_path / "settings"
    backdrop.set_modal_blur(before)


def _blur_action(shell):
    return next(a for a in shell._theme_actions() if a.key == "style_modal_blur")


def test_the_styles_menu_switches_the_blur_and_keeps_it(_settings, monkeypatch):
    from chisurf.core.settings import cs_settings
    from chisurf.core.settings import settings_utils

    monkeypatch.setattr(settings_utils, "get_path", lambda kind: _settings)
    monkeypatch.setitem(cs_settings, "gui", dict(cs_settings.get("gui") or {}))
    shell = EmtkShellApp({}, loader=lambda plugin_id: ImApp(lambda: None))
    try:
        action = _blur_action(shell)
        assert action.checked() is True, "on by default"
        action.run()
        assert backdrop.modal_blur() is False and action.checked() is False
        saved = yaml.safe_load((_settings / "settings_chisurf.yaml").read_text())
        assert saved["gui"]["modal_blur"] is False
        assert cs_settings["gui"]["modal_blur"] is False
    finally:
        shell.close()
    again = EmtkShellApp({}, loader=lambda plugin_id: ImApp(lambda: None))
    try:
        assert backdrop.modal_blur() is False, "the next shell starts with the saved choice"
    finally:
        again.close()
