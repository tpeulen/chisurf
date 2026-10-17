"""The data-loading settings model persists what it is given."""

from __future__ import annotations


def test_settings_model_setter_persists(monkeypatch):
    from chisurf.core.fio import staging_settings as sls

    saved = {}
    monkeypatch.setattr(sls, "set_data_loading_settings", lambda d: saved.update(d))

    model = sls.DataLoadingSettingsModel()
    model.threshold_mbps = 55.0
    model.min_size_mb = 16.0
    assert saved["threshold_mbps"] == 55.0
    assert saved["min_size"] == 16 * 1024 * 1024
