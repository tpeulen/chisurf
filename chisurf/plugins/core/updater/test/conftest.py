"""Every test of the updater plugin runs on fakes: no update, install, removal, environment change or network (see fakes.py)."""

import pytest

from .fakes import Fakes, hermetic_environment


@pytest.fixture(autouse=True)
def fakes(tmp_path, monkeypatch):
    """Temporary settings and HOME, and the fakes of every system action, for every test of this folder."""
    hermetic_environment(tmp_path, monkeypatch)
    return Fakes().install(monkeypatch)
