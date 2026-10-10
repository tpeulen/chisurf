"""Keep every core-plugin test off the user's real ``~/.chisurf``.

Core plugins read and write per-user state -- the settings YAML, the ``plugin_*_settings.ini`` window
geometries, the agent chat history, the documentation index, the MMFDB database, the light-path
``settings/`` folder. A test that touches the real folder changes the settings of the person running the
suite, so the whole tree is redirected to a scratch folder *before* ``chisurf.core.settings`` is first
imported (it resolves its paths once, at import). An explicit ``CHISURF_SETTINGS_DIR`` /
``MMFDB_SETTINGS_DIR`` in the environment wins, which is how a plugin's own ``conftest.py`` or a test
points the same lookups elsewhere.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

if "CHISURF_SETTINGS_DIR" not in os.environ:
    _SCRATCH = tempfile.mkdtemp(prefix="chisurf-core-tests-")
    atexit.register(shutil.rmtree, _SCRATCH, ignore_errors=True)
    os.environ["CHISURF_SETTINGS_DIR"] = os.path.join(_SCRATCH, "settings")
    os.environ.setdefault("MMFDB_SETTINGS_DIR", os.path.join(_SCRATCH, "settings"))
