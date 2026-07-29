"""Resetting the settings must not delete the user's data (RF-934).

``~/.chisurf`` is not settings-only: it also holds the per-user MMFDB database
(``flr/``), the content-addressed object store (``objects/``), the installed
user plugins (``plugins/``) and the fetched-structure cache (``structures/``).
``clear_settings_folder`` used to ``rmtree`` *every* direct child directory, so
"Reset local settings" — and the "Clear settings" button offered by the
startup-failure dialog — silently wiped all four and then reported success.

These tests pin the keep-list, and pin that the dedicated plugins action points
at the directory plugins are actually loaded from.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.core.settings import cleanup


@pytest.fixture
def settings_dir(tmp_path, monkeypatch) -> pathlib.Path:
    """Seed an isolated settings folder with user data *and* settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    for relative in (
        "flr/sample_management.db",
        "objects/ab/cd/blob.bin",
        "plugins/my_plugin/__init__.py",
        "structures/148L.pdb",
        "cache/analysis/entry.json",
        "logs/chisurf.log",
        "settings_chisurf.yaml",
        "chisurf.log",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("payload", encoding="utf-8")
    return tmp_path


def test_user_data_survives_a_settings_reset(settings_dir) -> None:
    """The four user-data directories are not settings and are kept."""
    cleanup.clear_settings_folder()
    assert (settings_dir / "flr/sample_management.db").is_file()
    assert (settings_dir / "objects/ab/cd/blob.bin").is_file()
    assert (settings_dir / "plugins/my_plugin/__init__.py").is_file()
    assert (settings_dir / "structures/148L.pdb").is_file()


def test_settings_are_still_cleared(settings_dir) -> None:
    """Everything that *is* a settings artefact still goes, log files stay."""
    cleanup.clear_settings_folder()
    assert not (settings_dir / "settings_chisurf.yaml").exists()
    assert not (settings_dir / "cache").exists()
    assert (settings_dir / "chisurf.log").is_file()


def test_keep_list_matches_the_directories_that_hold_user_data() -> None:
    """The keep-list is the contract - spell it out so a rename cannot drop one."""
    assert cleanup.USER_DATA_DIRS == frozenset({"flr", "objects", "plugins", "structures"})


def test_clear_user_plugins_folder_clears_the_loaded_plugins_directory(
    settings_dir,
) -> None:
    """The dedicated action targets the settings folder's ``plugins``.

    It used to point at ``~/.cs/plugins``, a directory nothing ever creates, so
    "Clear user plugins" was a no-op — invisible while the settings reset was
    deleting the plugins anyway, load-bearing now that it no longer does.
    """
    cleanup.clear_user_plugins_folder()
    assert not (settings_dir / "plugins/my_plugin").exists()
    assert (settings_dir / "plugins").is_dir()
