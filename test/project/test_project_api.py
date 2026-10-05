"""Local/hybrid API persistence uses the same scientific session as the server."""

from __future__ import annotations

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.api import ChiSurfAPI
from chisurf.core.data import DataCurve


@pytest.mark.parametrize("mode", ["local", "hybrid"])
def test_api_can_save_and_restore_its_local_session(mode, monkeypatch, tmp_path):
    curve = DataCurve(x=np.arange(5.0), y=np.arange(5.0) + 10.0, unique_identifier="api-data")
    monkeypatch.setattr(cs, "imported_datasets", [curve])
    monkeypatch.setattr(cs, "fits", [])
    api = ChiSurfAPI(mode=mode)
    target = tmp_path / "api.cs.pto"

    saved = api.save_project(str(target), "API project")
    assert saved["ok"] is True, saved
    assert target.is_file()
    cs.imported_datasets[:] = []
    loaded = api.load_project(str(target))
    assert loaded["ok"] is True, loaded
    assert loaded["dataset_count"] == 1
    assert cs.imported_datasets[0].unique_identifier == "api-data"
    np.testing.assert_array_equal(cs.imported_datasets[0].y, curve.y)


@pytest.mark.parametrize("mode", ["local", "hybrid"])
def test_session_restore_accepts_portable_project_in_local_modes(mode, monkeypatch, tmp_path):
    curve = DataCurve(x=np.arange(4.0), y=np.arange(4.0) + 2.0, unique_identifier="session-data")
    monkeypatch.setattr(cs, "imported_datasets", [curve])
    monkeypatch.setattr(cs, "fits", [])
    api = ChiSurfAPI(mode=mode)
    target = tmp_path / "session.cs.pto"
    assert api.save_project(str(target))["ok"] is True
    cs.imported_datasets.clear()

    restored = api.session_restore(str(target))
    assert restored["ok"] is True, restored
    assert cs.imported_datasets[0].unique_identifier == "session-data"


@pytest.mark.parametrize("mode", ["local", "hybrid"])
def test_api_failed_load_preserves_its_session(mode, monkeypatch, tmp_path):
    curve = DataCurve(x=np.arange(3.0), y=np.arange(3.0))
    monkeypatch.setattr(cs, "imported_datasets", [curve])
    monkeypatch.setattr(cs, "fits", [])
    api = ChiSurfAPI(mode=mode)
    bad = tmp_path / "bad.cs.pto"
    bad.write_bytes(b"broken PTO")
    assert api.load_project(str(bad))["ok"] is False
    assert cs.imported_datasets == [curve]
