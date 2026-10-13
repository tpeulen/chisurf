"""Every test of this plugin runs hermetic: settings, MMFDB and HOME in a temporary folder.

The native app persists through the ChiSurf settings folder and works in ``~/.hydropp_gui``, so a test that runs it
must never reach the owner's own; ``test_guard_real_state`` proves it. The fixtures here make the isolation the
default.
"""

from __future__ import annotations

import pytest

from . import hermetic


@pytest.fixture(scope="session", autouse=True)
def hydropro_session_isolation(tmp_path_factory):
    """The same isolation for module- and session-scoped fixtures."""
    import os

    tmp = tmp_path_factory.mktemp("hydropro_session")
    saved = {key: os.environ.get(key) for key in hermetic.env_for(tmp)}
    os.environ.update(hermetic.env_for(tmp))
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def hydropro_hermetic(tmp_path, monkeypatch):
    for key, value in hermetic.env_for(tmp_path).items():
        monkeypatch.setenv(key, value)
    yield
