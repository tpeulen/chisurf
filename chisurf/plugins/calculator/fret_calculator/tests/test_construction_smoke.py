"""Construction smoke test for the FRET Calculator (native emtk app).

Builds the real app headlessly to catch import / side-effect-on-init regressions and pins the
headless import boundary: the plugin package (``api`` / ``core`` / ``backend``) imports without a
Qt binding. The Qt dock-tool tests (``ChisurfDockTool`` reuse, the dropped-path message) went with
the Qt tool; the drop message is tested on the native app
(``test_a_file_dropped_on_the_host_reaches_the_app_and_says_the_calculator_has_no_file_input``).
"""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


def test_the_app_constructs_with_two_tabs_and_computed_defaults() -> None:
    """Two calculator tabs; the hetero one carries the donor lifetime in ns and a real efficiency."""
    from chisurf.plugins.calculator.fret_calculator.gui.app import make_app

    app = make_app(restore=False)
    hetero, homo = app.model.hetero, app.model.homo
    assert hetero.tau0 == 4.0
    assert 0.0 < hetero.E < 1.0
    assert homo.k_homo > 0.0


def test_package_root_has_no_qt_tool() -> None:
    """The package root no longer exposes a Qt tool."""
    import chisurf.plugins.calculator.fret_calculator as plugin

    with pytest.raises(AttributeError):
        plugin.FretCalculatorTool


def test_package_root_imports_without_qt() -> None:
    """Importing the plugin root must not pull in Qt.

    Run in a clean subprocess so modules imported by other tests do not mask the boundary.
    """
    code = (
        "import sys\n"
        "import chisurf.plugins.calculator.fret_calculator as p\n"
        "assert p.name\n"
        "mods = [m for m in sys.modules if m.split('.')[0] in ('qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6')]\n"
        "assert not mods, mods\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
