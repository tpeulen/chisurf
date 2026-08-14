"""Shared fixtures for the chimol suite: keep tests off the user's real prefs.

App-level fixtures build the real ``MolViewPluginWindow``, which enables
window-state persistence -- so without isolation a test *reads* whatever
layout the user's last live session saved (a closed density window made seven
body-press tests fail), and the first drag in a test *rewrites* the user's
real preferences. Both directions are wrong, so every chimol test runs
against a throwaway settings directory unless the caller already pinned one.

Two things about *how* this is done are load-bearing, and both were wrong
before -- the isolation existed, was described exactly as above, and did not
work:

**The variable is chimol's own.** This set only ``CHISURF_SETTINGS_DIR``,
which :mod:`chimol.settings_dir` has never read -- it reads
``CHIMOL_SETTINGS_DIR``. So the override never applied to chimol's own files
and every test read ``~/.chisurf/chimol_display.json``. It cost two failures
that looked like product defects: a background asserted black against a real
saved white, and a surface quality asserted ``splat`` against a real saved
``fast``. Both pass or fail depending on whose machine runs them, which is the
worst way for a test to be wrong.

``CHISURF_SETTINGS_DIR`` is still set below, for ChiSurf's own half.

The environment is also the *right* layer to isolate at, rather than calling
``settings_dir.set_settings_dir``: importing ``chisurf.plugins.chimol`` injects
ChiSurf's directory as a side effect, and most of these tests import it. The
environment wins over an injected directory precisely so a later import cannot
undo the isolation.

**The directory is set at import, not in a fixture.** ``_DISPLAY_CONFIG`` is
module-level state, loaded the first time :mod:`chimol.config` is imported --
which happens while pytest *collects*, before any fixture runs. A
session-scoped ``autouse`` fixture is therefore already too late. ``conftest``
is imported before the test modules beside it, so the assignment below happens
in time.
"""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest

#: Set at import time, for the reason in the module docstring. ``setdefault``
#: so a caller who pinned a directory keeps it -- including the one CI uses.
_SETTINGS_TMP = tempfile.mkdtemp(prefix="chimol-test-settings-")
_OWNED = []
for _var in ("CHIMOL_SETTINGS_DIR", "CHISURF_SETTINGS_DIR"):
    if not os.environ.get(_var):
        os.environ[_var] = _SETTINGS_TMP
        _OWNED.append(_var)


@pytest.fixture(scope="session", autouse=True)
def _isolated_chisurf_settings():
    """Tidy up what the import-time assignment above created."""
    yield
    for var in _OWNED:
        os.environ.pop(var, None)
    shutil.rmtree(_SETTINGS_TMP, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _settings_isolation_actually_took(_isolated_chisurf_settings):
    """Fail loudly if chimol is still reading the real settings directory.

    A guard rather than a comment, because the failure this prevents is
    invisible: nothing errors, the suite simply starts asserting against
    whatever the developer last clicked. The previous isolation was broken for
    however long ``CHIMOL_SETTINGS_DIR`` has existed and nobody noticed, since
    the tests only fail on a machine whose saved settings happen to disagree.
    """
    from chimol.settings_dir import settings_dir

    resolved = settings_dir()
    assert str(resolved).startswith(tempfile.gettempdir()) or str(resolved) == os.environ.get(
        "CHIMOL_SETTINGS_DIR", ""
    ), (
        f"chimol tests are reading {resolved}, which is a real settings "
        "directory. Every assertion about a default is now a statement about "
        "whoever ran them last."
    )
