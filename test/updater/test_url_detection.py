"""Telling a local update folder from a remote update URL.

This was a script: ``test_url_detection(url, expected_is_local)`` took two
arguments and was *called* from a module-level loop that printed PASS/FAIL and a
tally. pytest collected the function anyway, read its arguments as fixtures, and
errored with "fixture 'url' not found" — while the real checking happened at
import time, where a mismatch printed "FAIL" and changed nothing. It had been
printing FAIL for every local-folder case on this machine for as long as the
file existed, for two reasons the script could not surface:

* ``ChiSurfUpdater(update_url=...)`` **ignores that argument** by design — its
  docstring says so — and always uses the hardcoded remote URL. So every case
  the script "checked" was really checking the same hardcoded URL, and the
  remote cases passed vacuously.
* ``_is_local_folder`` is platform-aware. ``Q:\\chisurf`` is a local folder on
  Windows and is not one on macOS or Linux, which is correct: there is no drive
  Q: here.

So the URL is set on the instance, and the platform-specific cases say which
platform they mean.
"""

import platform

import pytest

from chisurf.plugins.core.updater.updater import ChiSurfUpdater


def _updater_for(url):
    """An updater whose ``update_url`` really is *url*.

    The constructor argument is ignored on purpose, so it has to be assigned.
    """
    updater = ChiSurfUpdater()
    updater.update_url = url
    return updater


REMOTE_URLS = [
    "https://www.peulen.xyz/downloads/chisurf/conda/",
    "http://example.com/chisurf/",
    "ftp://example.com/chisurf/",
    "https://github.com/Fluorescence-Tools/chisurf/releases/conda",
]

WINDOWS_PATHS = [
    "Q:\\chisurf\\conda",  # drive letter
    "C:\\Users\\user\\Documents",  # drive letter
    "\\\\server\\share\\folder",  # UNC share
]


@pytest.mark.parametrize("url", REMOTE_URLS)
def test_a_remote_url_is_not_a_local_folder(url):
    assert _updater_for(url)._is_local_folder() is False


def test_an_existing_directory_is_a_local_folder(tmp_path):
    """True on every platform: the path exists and is a directory."""
    assert _updater_for(str(tmp_path))._is_local_folder() is True


@pytest.mark.skipif(platform.system().lower() != "windows", reason="Windows path shapes")
@pytest.mark.parametrize("path", WINDOWS_PATHS)
def test_windows_path_shapes_are_local_folders(path):
    """Drive letters and UNC shares count even when they do not exist yet.

    The drive letter is the case worth naming: ``Q:\\chisurf`` contains a colon,
    so a rule written as "reject anything with a colon" would call it remote.
    """
    assert _updater_for(path)._is_local_folder() is True


@pytest.mark.skipif(platform.system().lower() == "windows", reason="POSIX path shapes")
def test_windows_path_shapes_are_not_local_folders_off_windows():
    """And they must *not* count elsewhere — there is no drive Q: here."""
    for path in WINDOWS_PATHS:
        assert _updater_for(path)._is_local_folder() is False


@pytest.mark.skipif(platform.system().lower() == "windows", reason="POSIX path shapes")
def test_a_posix_absolute_path_is_a_local_folder_even_if_absent():
    assert _updater_for("/nonexistent/update/folder")._is_local_folder() is True


def test_the_constructor_ignores_the_update_url_argument():
    """Pins documented-but-surprising behaviour.

    ``ChiSurfUpdater(update_url=...)`` looks like it sets the URL and does not.
    Anyone writing a test against a local folder will otherwise be testing the
    hardcoded remote URL without noticing — which is exactly what the script
    this file replaced did.
    """
    updater = ChiSurfUpdater(update_url="/some/local/folder")
    assert updater.update_url.startswith("https://")
