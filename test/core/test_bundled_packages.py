"""Source companions preserve launcher and test-package import precedence."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import chisurf._bundled_packages as bundled


def _checkout(tmp_path, monkeypatch):
    """Build actual companion directories with a synthetic launcher's first path."""
    package = tmp_path / "chisurf"
    package.mkdir()
    monkeypatch.setattr(bundled, "__file__", str(package / "_bundled_packages.py"))
    for name, source in bundled._BUNDLED_PACKAGE_PATHS:
        directory = tmp_path / "modules" / name
        if source:
            directory /= source
        directory.mkdir(parents=True)
    monkeypatch.setattr(sys, "path", ["launcher-first", *sys.path])
    return tmp_path


def test_launcher_entry_precedes_source_companions(tmp_path, monkeypatch):
    """A companion's test package never outranks the launcher's own package."""
    _checkout(tmp_path, monkeypatch)
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    added = bundled.bootstrap_bundled_packages()
    assert added
    assert sys.path[0] == "launcher-first"
    assert sys.path[1 : 1 + len(added)] == [str(path) for path in added]
    assert bundled.bootstrap_bundled_packages() == ()


def test_editable_ndxplorer_needs_no_additional_root(tmp_path, monkeypatch):
    """The editable finder already resolves ndxplorer without a sibling test root."""
    root = _checkout(tmp_path, monkeypatch)
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name: object() if name == "ndxplorer" else None
    )
    added = bundled.bootstrap_bundled_packages()
    assert root / "modules" / "ndxplorer" not in added
    assert str(root / "modules" / "ndxplorer") not in sys.path


def test_cold_plugin_import_preserves_launcher_and_test_namespace(tmp_path):
    """Plugin-first imports resolve ChiSurf test.gui without an import-order workaround."""
    root = Path(__file__).resolve().parents[2]
    code = """
import importlib, sys
first = sys.path[0]
importlib.import_module('chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data')
assert sys.path[0] == first, (first, sys.path[0])
module = importlib.import_module('test.gui')
assert module.__file__.startswith(sys.argv[1]), module.__file__
"""
    environment = dict(
        os.environ,
        CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
        MMFDB_SETTINGS_DIR=str(tmp_path / "metadata"),
        QT_QPA_PLATFORM="offscreen",
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(root)],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
