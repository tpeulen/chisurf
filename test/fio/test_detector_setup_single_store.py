"""The RPC service and every setup picker read and write one detector-setup store."""

import pytest


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Point the store at a scratch MMFDB and settings folder."""
    import chisurf.core.data_io.detector_setups as store

    monkeypatch.setattr(store, "DETECTOR_SETUPS_FILE", tmp_path / "detector_setups.json")
    monkeypatch.setattr(store.DETECTOR_CONFIG, "canonical_file", tmp_path / "detector_setups.json")
    path = str(tmp_path / "setups.mmfdb")
    real = store._db
    monkeypatch.setattr(store, "_db", lambda db_path=None: real(db_path or path))
    return path


SETUP = {"detectors": {"green": {"chs": [0, 2], "micro_time_ranges": [[0, 4096]]}},
         "windows": {"prompt": [0, 2048]}}


def test_rpc_save_is_visible_in_the_picker_loader(db_path):
    """A setup saved through the server service is listed by the GUI picker path."""
    from chisurf.gui.widgets.setup_selector import _default_loader as _load_setups
    from chisurf.server.services.detector_setups import save_setup
    from chisurf.server.session import SessionState

    result = save_setup(SessionState(), "ALEX run", SETUP)
    assert result["ok"], result
    listed = _load_setups(None)["setups"]
    assert listed["ALEX run"]["detectors"]["green"]["chs"] == [0, 2]


def test_rejected_store_write_is_reported(db_path, monkeypatch):
    """A store that refuses the write is a service error, never a silent success."""
    import chisurf.core.data_io.detector_setups as store
    from chisurf.server.services.detector_setups import save_setup
    from chisurf.server.session import SessionState

    monkeypatch.setattr(store, "save_setups", lambda *a, **k: False)
    assert not save_setup(SessionState(), "broken", SETUP)["ok"]


def test_without_mmfdb_save_and_load_share_the_json_file(tmp_path, monkeypatch):
    """With no database both directions fall back to the same canonical JSON file."""
    import chisurf.core.data_io.detector_setups as store

    monkeypatch.setattr(store, "DETECTOR_SETUPS_FILE", tmp_path / "detector_setups.json")
    monkeypatch.setattr(store, "_db", lambda db_path=None: None)
    assert store.save_detector_setups({"setups": {"a": SETUP}, "last_used": "a"})
    assert store.save_detector_setups({"setups": {"b": SETUP}})
    loaded = store.load_detector_setups()
    assert set(loaded["setups"]) == {"a", "b"} and loaded["last_used"] == "a"
