"""Where chimol's command-line history lives.

Its own module because the *legacy* path matters: the file was once called
``molview_cmd_history``, and a user who has been running chimol since then still
has one. Dropping the fallback would silently lose their history, which is the
kind of loss nobody reports as a bug -- they just find the Up arrow empty one
day.
"""

from __future__ import annotations

import pathlib

__all__ = ["resolve_history_path"]


def resolve_history_path() -> pathlib.Path | None:
    """Return the chimol command-history file.

    Returns
    -------
    pathlib.Path or None
        The pre-rename file when it exists and the current one does not, so an
        existing history keeps being read and is migrated on the next write.
        ``None`` when no writable location can be determined, which disables
        persistence rather than failing.
    """
    try:
        # Through `chimol.settings_dir`, not ChiSurf directly: it already
        # resolves the env override a test sets, ChiSurf's directory when
        # ChiSurf is importable, and a standalone fallback. The home-directory
        # branch this replaces missed the override, so a suite wrote history
        # into the developer's own home.
        from ..settings_dir import settings_dir as _settings_dir  # noqa: PLC0415

        base = _settings_dir()
        current = base / "chimol_cmd_history.txt"
        legacy = base / "molview_cmd_history.txt"

        if not current.exists() and legacy.exists():
            return legacy
        return current
    except Exception:
        return None
