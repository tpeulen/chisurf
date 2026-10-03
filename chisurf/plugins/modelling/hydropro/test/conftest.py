"""Every test of this plugin runs hermetic: settings, MMFDB, HOME and QSettings in a temporary folder.

The Qt tool persists through ``QSettings`` (a real plist on macOS), so a test that builds or runs it must never reach
the owner's preferences; ``test_guard_real_state`` proves it. The fixtures here make the isolation the default.
"""

from __future__ import annotations

import pytest

from . import hermetic


@pytest.fixture(scope="session", autouse=True)
def hydropro_session_isolation(tmp_path_factory):
    """The same isolation for module- and session-scoped fixtures (a Qt tool built once per module)."""
    import os

    tmp = tmp_path_factory.mktemp("hydropro_session")
    saved = {key: os.environ.get(key) for key in hermetic.env_for(tmp)}
    os.environ.update(hermetic.env_for(tmp))
    try:
        hermetic.isolate(tmp)
    except Exception:
        pass
    yield
    hermetic.restore()
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def hydropro_hermetic(tmp_path, monkeypatch):
    for key, value in hermetic.env_for(tmp_path).items():
        monkeypatch.setenv(key, value)
    try:
        import qtpy  # noqa: F401
    except Exception:  # Qt-free runs
        yield
        return
    hermetic.isolate(tmp_path)  # stays in force after the test: a module fixture built later must not see Qt's real settings
    yield
