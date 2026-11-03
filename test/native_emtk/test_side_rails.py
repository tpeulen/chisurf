"""Every navigation rail beside a tool resizes by its edge and folds to its icons when narrow.

One behaviour (:class:`chisurf.emtk.side_rail.SideRail`) for the step hub, Settings, Imaging Tools
and the MMFDB admin: the edge is grabbed on either side of the line, narrower than ``FOLD`` the
rail folds to a strip of icons, and the width the user chose is in the tool's settings.
"""

from __future__ import annotations

import pytest
from emtk.events import LEFT_BUTTON
from emtk.testing import Driver

from chisurf.emtk.side_rail import FOLD, FOLDED, GRIP


@pytest.fixture(autouse=True)
def _private_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()


def _settings():
    from chisurf.plugins.core.setup.gui.app import UnifiedSettingsApp

    return UnifiedSettingsApp()


def _imaging():
    from chisurf.plugins.microscopy.imaging_tools.gui.app import make_app

    return make_app()


def _mmfdb():
    from chisurf.plugins.core.mmfdb_admin.gui.app import make_app

    return make_app()


def _drag(drv, x0, dx, y):
    drv.hover((x0, y))
    drv.surface.on_pointer_press(x0, y, LEFT_BUTTON, 0)
    drv.frame()
    for k in range(1, 9):
        drv.surface.on_pointer_move(x0 + dx * k / 8, y, LEFT_BUTTON, 0)
        drv.frame()
    drv.surface.on_pointer_release(x0 + dx, y, LEFT_BUTTON, 0)
    drv.frame(3)


@pytest.mark.parametrize("make", [_settings, _imaging, _mmfdb], ids=["settings", "imaging", "mmfdb"])
def test_the_rail_drags_folds_unfolds_and_is_saved(make):
    app = make()
    try:
        drv = Driver(app, size=(1200, 700))
        drv.draw(4)
        rail = app.rail
        left = rail.left
        y = 400.0
        _drag(drv, left + GRIP / 2, 80, y)  # grabbed over the tool
        assert rail.width == pytest.approx(left + 80) and not rail.folded
        _drag(drv, left + 80 - GRIP / 2, -40, y)  # grabbed over the rail
        assert rail.width == pytest.approx(left + 40)
        assert app.export_settings()["rail_width"] == pytest.approx(left + 40)
        _drag(drv, left + 40, -(left + 40 - FOLD) - 40, y)
        assert rail.folded and rail.left == FOLDED
        drv.draw(2)
        _drag(drv, FOLDED, 200, y)
        assert not rail.folded
    finally:
        close = getattr(app, "close", None)
        if callable(close):
            close()
