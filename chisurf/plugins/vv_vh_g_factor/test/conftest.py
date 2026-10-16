import pytest

@pytest.fixture(autouse=True)
def hermetic_env(tmp_path, monkeypatch):
    import chisurf.core.settings as settings

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path / "settings", raising=False)
    (tmp_path / "settings").mkdir(exist_ok=True)
    (tmp_path / "home").mkdir(exist_ok=True)
