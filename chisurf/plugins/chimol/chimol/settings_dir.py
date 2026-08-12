"""Where chimol keeps a user's settings, with or without ChiSurf around it.

Why this exists
---------------
chimol has two homes. Inside ChiSurf it is a plugin and its settings belong
with everything else the application keeps, in ``~/.chisurf``. Run on its own
-- ``python -m chisurf.plugins.chimol.chimol``, with no toolkit and no host
application -- there is no ChiSurf to ask.

Both places that needed a directory resolved it the same way and returned
``None`` when ChiSurf was missing: :func:`chimol.config.get_user_display_config_path`
and :func:`chimol.renderer.window_state.state_path`. ``None`` meant "do not
persist", so **standalone chimol silently forgot every setting and every window
position between runs** -- the display config fell back to the package copy,
which is shared by every install and must not be written to, and the window
layout was simply lost. Nothing failed; the settings just never came back.

So the fallback is a real directory rather than ``None``:

* ``$CHIMOL_SETTINGS_DIR`` when set -- which is also what a test sets, so a
  suite never writes into the developer's own configuration;
* ``~/.chisurf`` when ChiSurf is importable, so the plugin and the standalone
  run share one file and one set of settings;
* ``~/.chimol`` otherwise -- hidden, as a dotfile directory is.

The directory is created on demand, not at import: resolving where settings
*would* go is a question worth answering without leaving a directory behind for
someone who only asked.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

__all__ = ["settings_dir", "settings_path"]

logger = logging.getLogger(__name__)

#: Overrides everything. A test sets this so the suite cannot write into the
#: real configuration -- the failure it prevents is a test that "passes" by
#: overwriting the window layout of whoever ran it.
ENV_VAR = "CHIMOL_SETTINGS_DIR"

#: The standalone home. Hidden, beside the other dotfile directories.
FALLBACK = "~/.chimol"


def settings_dir(create: bool = False) -> Path:
    """Return the directory chimol's user settings live in.

    Parameters
    ----------
    create : bool, optional
        Create the directory (and its parents) if it is missing. Left ``False``
        for callers that only want to *read*, so asking where settings would go
        does not create a directory for someone who never saves one.

    Returns
    -------
    pathlib.Path
        An absolute path. Always a real directory -- never ``None`` -- so a
        caller cannot accidentally treat "nowhere to save" as "do not save".
    """
    override = os.environ.get(ENV_VAR, "").strip()
    if override:
        path = Path(override).expanduser()
    else:
        path = _chisurf_settings_dir() or Path(FALLBACK).expanduser()

    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            # A read-only home is survivable: settings stop persisting, which
            # is what happened before this module existed. It must be said out
            # loud rather than swallowed, because the symptom otherwise is
            # "chimol forgets things" with nothing anywhere to explain it.
            logger.warning("chimol cannot create %s; settings will not persist", path)
    return path


def settings_path(name: str, create: bool = False) -> Path:
    """Return the full path of one settings file.

    Parameters
    ----------
    name : str
        A file name, e.g. ``"chimol_display.json"``.
    create : bool, optional
        Create the containing directory. Pass ``True`` when about to write.

    Returns
    -------
    pathlib.Path
    """
    return settings_dir(create=create) / str(name)


def _chisurf_settings_dir() -> Path | None:
    """ChiSurf's settings directory, or ``None`` when it is not importable.

    Returns
    -------
    pathlib.Path or None
    """
    try:
        import chisurf.core.settings as _cs_settings  # noqa: PLC0415

        return Path(_cs_settings.get_path("settings"))
    except Exception:  # noqa: BLE001 - standalone chimol, or a partial install
        return None
