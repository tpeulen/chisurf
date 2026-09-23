"""The Qt-free core's settings import without the GUI package beside them.

A browser page (``python -m ndxplorer.app.web``) ships ``chisurf.core`` and
not ``chisurf.gui``. Importing the settings used to copy the Qt style sheets
out of ``chisurf/gui/styles`` unconditionally, so the core failed at import
wherever the GUI was not installed -- and every ndX feature that needs
``chisurf.core`` went quiet with it.
"""

from __future__ import annotations

from chisurf.core.settings import settings_utils


def test_copying_styles_without_a_gui_package_is_a_no_op(tmp_path, monkeypatch):
    fake = tmp_path / "chisurf" / "core" / "settings" / "settings_utils.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("")
    monkeypatch.setattr(settings_utils, "__file__", str(fake))
    called = []
    monkeypatch.setattr(settings_utils, "get_path", lambda *a, **k: called.append(a))
    settings_utils.copy_styles_to_user_folder()
    assert not called, "it went on to the user folder with nothing to copy"
