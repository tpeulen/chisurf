"""The operator can change both measurement paths in an acquisition JSON profile."""
import json
from pathlib import Path

import pytest

from chisurf.plugins.core.acq.live.storage_config import StorageConfig, StorageConfigError


def test_windows_paths_are_read_literally_from_profile(tmp_path):
    profile = tmp_path / 'instrument.json'
    profile.write_text(json.dumps({'storage': {'local_directory': r'C:\Measurements',
                                               'archive_directory': r'Z:\microtime200'}}))
    config = StorageConfig.from_file(profile)
    assert config.local_directory == r'C:\Measurements'
    assert config.archive_directory == r'Z:\microtime200'


def test_explicitly_missing_archive_or_local_is_rejected(tmp_path):
    profile = tmp_path / 'instrument.json'
    profile.write_text(json.dumps({'storage': {'local_directory': 'C:/Measurements'}}))
    with pytest.raises(StorageConfigError, match='archive_directory'):
        StorageConfig.from_file(profile)


def test_invalid_values_are_rejected(tmp_path):
    profile = tmp_path / 'instrument.json'
    profile.write_text(json.dumps({'storage': {'local_directory': '', 'archive_directory': 12}}))
    with pytest.raises(StorageConfigError):
        StorageConfig.from_file(profile)


def test_absent_storage_is_not_silently_defaulted(tmp_path):
    profile = tmp_path / 'instrument.json'
    profile.write_text('{}')
    with pytest.raises(StorageConfigError, match='storage'):
        StorageConfig.from_file(profile)


def test_loading_profile_applies_both_paths_without_hardware(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    profile = tmp_path / 'instrument.json'
    local, archive = str(tmp_path / 'local'), str(tmp_path / 'archive')
    profile.write_text(json.dumps({'schema': 'chisurf.acquisition/1',
                                   'storage': {'local_directory': local, 'archive_directory': archive}}))
    model = RecordModel(output_dir=tmp_path / 'old', realtime=False)
    monkeypatch.setattr(model, '_picked', lambda: ('profile', str(profile)))
    monkeypatch.setattr(model, 'adopt_settings', lambda *_: True)
    assert model.load_settings()
    assert model.output_dir == Path(local)
    assert model.archive_directory == archive
    assert not Path(local).exists() and not Path(archive).exists()
