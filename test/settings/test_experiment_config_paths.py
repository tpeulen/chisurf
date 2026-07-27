"""The packaged experiment configuration must actually be found (RF-022/RF-264).

``chisurf/gui/main_helper.py`` used to resolve the shipped defaults through
``get_path('cs')`` — not a valid ``path_type``, so the old catch-all branch
returned ``~/.chisurf`` and ``source_config_file`` pointed at a file that never
exists. Nothing raised: the startup "experiment configuration update available"
prompt simply never fired, the first-run copy was never seeded, and the merge
with the shipped defaults silently degenerated to the user's own (possibly
years-old) copy — offering experiments whose readers and models had since been
renamed or removed.

These tests pin both halves: the single resolver every consumer now uses, and
the fact that a mistyped ``path_type`` fails loudly instead of resolving to the
settings directory.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from chisurf.core.experiments import get_experiment_config_files
from chisurf.core.settings import path_utils


def test_packaged_experiment_config_exists() -> None:
    """The packaged half of the pair resolves to a real, parseable YAML file."""
    packaged, _ = get_experiment_config_files()
    assert packaged.is_file(), f"packaged experiment configuration missing: {packaged}"
    config = yaml.safe_load(packaged.read_text(encoding="utf-8"))
    assert isinstance(config, dict) and config


def test_user_experiment_config_follows_the_settings_directory(tmp_path, monkeypatch) -> None:
    """The user half lives in the settings directory, override included."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    packaged, user = get_experiment_config_files()
    assert user == tmp_path / "experiment_configs.yaml"
    assert user != packaged


def test_gui_and_bootstrap_resolve_the_same_files() -> None:
    """Every consumer of the pair goes through the one resolver.

    The GUI (``init_setups``) is not importable without Qt here, so this pins
    the seam it now uses: the agent bootstrap and the experiment-type registry
    must see the very same packaged file, otherwise a renamed experiment
    reaches one of them and not the other.
    """
    packaged, user = get_experiment_config_files()
    source = pathlib.Path(path_utils.__file__).parent / "experiment_configs.yaml"
    assert packaged == source
    assert user.parent == path_utils.get_path("settings")


def test_unknown_path_type_raises() -> None:
    """A mistyped path type raises instead of silently yielding the settings dir."""
    with pytest.raises(ValueError):
        path_utils.get_path("cs")
