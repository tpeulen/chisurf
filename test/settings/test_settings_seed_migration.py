"""The user settings file holds what the user changed, and nothing else.

Until 26.1 the first start copied the packaged ``settings_chisurf.yaml`` into
the settings folder. Loading overlays the user file on the defaults, so every
copied default was pinned as if chosen: when the plot backend default moved
from pyqtgraph to emtk, every existing install kept pyqtgraph.
"""

from __future__ import annotations

import pathlib

import yaml

from chisurf.core.settings import settings_utils

PACKAGED = pathlib.Path(settings_utils.__file__).parent / "settings_chisurf.yaml"


def _defaults() -> dict:
    return yaml.safe_load(PACKAGED.read_text(encoding="utf-8"))


def test_a_seeded_copy_follows_the_new_defaults_and_keeps_real_changes(tmp_path):
    seeded = _defaults()
    seeded["gui"]["plot"]["backend"] = "pyqtgraph"  # the default of its day
    seeded["gui"]["language"] = "fr"  # something the user chose
    user_file = tmp_path / "settings_chisurf.yaml"
    user_file.write_text(yaml.safe_dump(seeded), encoding="utf-8")

    settings = settings_utils.get_chisurf_settings(user_file)

    assert settings["gui"]["plot"]["backend"] == _defaults()["gui"]["plot"]["backend"]
    assert settings["gui"]["language"] == "fr"
    # Migrated once: the file keeps only the change.
    assert yaml.safe_load(user_file.read_text(encoding="utf-8")) == {"gui": {"language": "fr"}}


def test_a_value_that_was_never_a_default_is_kept(tmp_path):
    user_file = tmp_path / "settings_chisurf.yaml"
    user_file.write_text(yaml.safe_dump({"gui": {"plot": {"backend": "wgpu"}}}), encoding="utf-8")

    assert settings_utils.get_chisurf_settings(user_file)["gui"]["plot"]["backend"] == "wgpu"


def test_no_user_file_is_the_defaults_and_creates_nothing(tmp_path):
    user_file = tmp_path / "settings_chisurf.yaml"

    assert settings_utils.get_chisurf_settings(user_file) == _defaults()
    assert not user_file.exists()


def test_seeding_the_settings_folder_does_not_copy_the_main_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    settings_utils.copy_settings_to_user_folder()

    assert not (tmp_path / "settings_chisurf.yaml").exists()
