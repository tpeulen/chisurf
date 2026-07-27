from __future__ import annotations

import os
import pathlib
import sys
import ctypes


USER_SETTINGS_EXISTED_BEFORE = None


def _set_hidden_on_windows(path: pathlib.Path) -> None:
    """Set the hidden attribute on Windows for the given path.

    This uses WinAPI via ctypes to OR the FILE_ATTRIBUTE_HIDDEN flag without
    clearing existing attributes.
    """
    if os.name != 'nt':
        return
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x2
        GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        SetFileAttributesW = ctypes.windll.kernel32.SetFileAttributesW
        GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
        GetFileAttributesW.restype = ctypes.c_uint32
        SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        SetFileAttributesW.restype = ctypes.c_int

        attrs = GetFileAttributesW(str(path))
        if attrs == 0xFFFFFFFF:  # INVALID_FILE_ATTRIBUTES
            return
        # OR the hidden flag
        SetFileAttributesW(str(path), attrs | FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        # Fail silently if we cannot set the attribute
        pass


def get_path(path_type: str = 'settings') -> pathlib.Path:
    """Get key chisurf paths.

    - For path_type == 'settings': returns the user settings dir '~/.chisurf'.
      Ensures it exists and marks it hidden on Windows (only when newly created).
    - For path_type == 'chisurf': returns the installed chisurf package directory.
      Never modifies attributes of the installed package directory.

    Any other ``path_type`` is a programming error and raises: the former
    catch-all silently returned the user settings directory, which turned a
    typo (``get_path('cs')``) into a path that merely never exists — the
    packaged experiment configuration was read from it and quietly ignored.

    Raises
    ------
    ValueError
        If ``path_type`` is neither ``'settings'`` nor ``'chisurf'``.
    """
    if path_type == 'settings':
        # Allow overriding the settings directory via the environment. This is the
        # single indirection point for redirecting all per-user state (database,
        # object store, settings files) — used by the hermetic test harness to keep
        # tests off the real ~/.chisurf, and available to users who want a custom
        # location.
        override = os.environ.get('CHISURF_SETTINGS_DIR')
        if override:
            path = pathlib.Path(override).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            return path
        path = pathlib.Path.home() / '.chisurf'
        existed_before = path.exists()
        global USER_SETTINGS_EXISTED_BEFORE
        if USER_SETTINGS_EXISTED_BEFORE is None:
            USER_SETTINGS_EXISTED_BEFORE = bool(existed_before)
        path.mkdir(parents=True, exist_ok=True)
        # Only set hidden for the user settings dir, and only if we created it now
        if not existed_before:
            _set_hidden_on_windows(path)
        return path

    elif path_type == 'chisurf':
        # Return the chisurf package root directory
        return pathlib.Path(__file__).parent.parent.parent
    else:
        raise ValueError(
            f"Unknown path_type {path_type!r}; expected 'settings' or 'chisurf'."
        )
