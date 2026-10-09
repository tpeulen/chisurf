"""Every test of the updater plugin runs on fakes: no update, install, removal, environment change or network (see fakes.py)."""

import pytest

from .fakes import Fakes, hermetic_environment


@pytest.fixture(autouse=True)
def fakes(tmp_path, monkeypatch):
    """Temporary settings and HOME, and the fakes of every system action, for every test of this folder."""
    hermetic_environment(tmp_path, monkeypatch)
    return Fakes().install(monkeypatch)


@pytest.fixture(autouse=True)
def nothing_ran(fakes):
    """After every test: no process was started and the elevated runner and the restart were never reached."""
    yield
    assert fakes.process_attempts == [], "a test tried to start a process"
    assert not [
        c for kind, c in fakes.update_commands if kind in ("run_command", "run_with_elevation")
    ]
    assert fakes.restarts == 0


@pytest.fixture(autouse=True)
def settings_restored():
    """``cs_settings`` is process-global: the updater section a test changes is put back afterwards."""
    import copy

    from chisurf.core.settings import cs_settings

    plugins = cs_settings.setdefault("plugins", {})
    had = "updater" in plugins
    saved = copy.deepcopy(plugins.get("updater"))
    yield
    if had:
        plugins["updater"] = saved
    else:
        plugins.pop("updater", None)
