"""Shared fixtures for the chimol suite: keep tests off the user's real prefs.

App-level fixtures build the real ``MolViewPluginWindow``, which enables
window-state persistence -- so without isolation a test *reads* whatever
layout the user's last live session saved (a closed density window made seven
body-press tests fail), and the first drag in a test *rewrites* the user's
real preferences. Both directions are wrong, so every chimol test runs
against a throwaway settings directory unless the caller already pinned one.
"""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolated_chisurf_settings():
    if os.environ.get("CHISURF_SETTINGS_DIR"):
        yield
        return
    with tempfile.TemporaryDirectory(prefix="chimol-test-settings-") as tmp:
        os.environ["CHISURF_SETTINGS_DIR"] = tmp
        try:
            yield
        finally:
            os.environ.pop("CHISURF_SETTINGS_DIR", None)
