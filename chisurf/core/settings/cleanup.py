from __future__ import annotations

import os
import shutil

import chisurf as cs

from .path_utils import get_path

#: Direct children of the settings folder that hold *user data*, not settings.
#: The settings folder is not settings-only: it is also where the per-user
#: metadata database, the content-addressed object store, the installed user
#: plugins and the fetched-structure cache live. Resetting the settings must
#: never delete those - they are unrecoverable user data, and every one of them
#: has its own dedicated clear action.
USER_DATA_DIRS = frozenset(
    {
        "flr",  # per-user MMFDB database (sample_management.db)
        "objects",  # content-addressed object store (embedded experimental data)
        "plugins",  # installed user plugins (see clear_user_plugins_folder)
        "structures",  # fetched-structure cache
    }
)


def clear_settings_folder():
    """
    Remove settings files and subdirectories inside the settings folder, but preserve log files.

    This function walks through the directory returned by `get_path()` and:
      - Recursively deletes each subdirectory (skipping over any files it cannot remove),
      - Deletes each settings file at the top level (skipping log files),
      - Logs a concise warning via `cs.logging.warning()` (max 128 chars)
        for any file or directory that cannot be deleted.

    The user-data directories listed in :data:`USER_DATA_DIRS` are **not**
    touched: the settings folder also hosts the metadata database, the object
    store, the user plugins and the structure cache, and "reset settings" is
    not "delete my data".

    The root settings folder itself is left intact, even if not empty.

    Raises:
        None. All deletion errors are caught and logged.
    """
    root = get_path()

    # Helper to warn on failed removals inside rmtree()
    def _handle_remove_error(func, path, exc_info):
        ex = exc_info[1]
        # Only skip PermissionErrors (file-in-use, etc.)
        if isinstance(ex, PermissionError):
            cs.logging.warning(f"Could not delete {path}: {ex}. Skipping.")
            return
        # Propagate everything else
        raise ex

    # If the root doesn't even exist, nothing to do
    if not os.path.isdir(root):
        return

    # Iterate through *direct* children of root
    for entry in os.scandir(root):
        path = entry.path
        try:
            if entry.is_dir(follow_symlinks=False):
                # Never sweep user data away with the settings
                if entry.name in USER_DATA_DIRS:
                    continue
                # Recursively remove this subfolder entirely (with our onerror)
                shutil.rmtree(path, onerror=_handle_remove_error)
            else:
                # Skip log files (files ending with .log)
                if not str(path).endswith(".log"):
                    # Remove a single file
                    os.unlink(path)
        except PermissionError:
            cs.logging.warning(f"Skipping locked file or folder: {path}")
        except OSError:
            # e.errno==ENOTEMPTY can happen if subdir isn't empty (due to skips)
            cs.logging.warning(f"Couldn't remove {path}")


def clear_user_plugins_folder():
    """
    Remove all contents of the user plugins folder ({settings}/plugins).

    This function removes all files and directories inside the user plugins
    directory but leaves the directory itself intact. The directory is the
    ``plugins`` folder of the settings directory, i.e. the ``~/.chisurf/plugins``
    that `chisurf.plugins` appends to its ``__path__`` - the former
    ``~/.cs/plugins`` never existed, so the menu action silently did nothing.

    Raises:
        None. All deletion errors are caught and logged.
    """
    user_plugins_dir = get_path("settings") / "plugins"

    # If the user plugins directory doesn't exist, nothing to do
    if not user_plugins_dir.is_dir():
        return

    # Helper to warn on failed removals inside rmtree()
    def _handle_remove_error(func, path, exc_info):
        ex = exc_info[1]
        # Only skip PermissionErrors (file-in-use, etc.)
        if isinstance(ex, PermissionError):
            cs.logging.warning(f"Could not delete {path}: {ex}. Skipping.")
            return
        # Propagate everything else
        raise ex

    # Iterate through *direct* children of user plugins directory
    for entry in os.scandir(user_plugins_dir):
        path = entry.path
        try:
            if entry.is_dir(follow_symlinks=False):
                # Recursively remove this subfolder entirely (with our onerror)
                shutil.rmtree(path, onerror=_handle_remove_error)
            else:
                # Remove a single file
                os.unlink(path)
        except PermissionError:
            cs.logging.warning(f"Skipping locked file or folder: {path}")
        except OSError:
            cs.logging.warning(f"Couldn't remove {path}")


def clear_logging_files():
    """
    Remove only log files inside the logs subfolder of the settings folder.

    This function walks through the logs directory inside the settings folder and:
      - Deletes each log file (files ending with .log or .py),
      - Logs a concise warning via `cs.logging.warning()` (max 128 chars)
        for any file that cannot be deleted.

    The logs folder itself is left intact, even if not empty.

    Raises:
        None. All deletion errors are caught and logged.
    """
    root = get_path()
    logs_folder = root / "logs"

    # If the logs folder doesn't exist, nothing to do
    if not os.path.isdir(logs_folder):
        return

    # Iterate through *direct* children of logs folder
    for entry in os.scandir(logs_folder):
        path = entry.path
        try:
            if not entry.is_dir(follow_symlinks=False):
                # Remove log files (files ending with .log) and session files (.py)
                if str(path).endswith(".log") or str(path).endswith(".py"):
                    os.unlink(path)
        except PermissionError:
            cs.logging.warning(f"Skipping locked file: {path}")
        except OSError:
            cs.logging.warning(f"Couldn't remove file: {path}")
