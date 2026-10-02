"""Keep every test of this plugin away from the user's real settings: HOME, the chisurf and MMFDB folders, QSettings."""

import pytest


@pytest.fixture(autouse=True)
def hermetic_user_state(tmp_path_factory, monkeypatch):
    tmp_path = tmp_path_factory.mktemp("user_state")   # not the test's own tmp_path: tests list that folder
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "home").mkdir()
    (tmp_path / "settings").mkdir()
    try:
        import chisurf.core.settings as settings

        monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path / "settings", raising=False)
    except Exception:  # pragma: no cover
        pass
    try:
        from qtpy import QtCore

        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
        QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(tmp_path / "qt"))
        QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, QtCore.QSettings.SystemScope, str(tmp_path / "qt"))
    except Exception:  # pragma: no cover
        pass
    yield
