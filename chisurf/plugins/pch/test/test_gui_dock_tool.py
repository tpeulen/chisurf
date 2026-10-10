"""The PCH package imports without a Qt binding (the window is the native emtk app)."""

import pathlib
import subprocess
import sys


def test_gui_package_root_imports_without_qt():
    """Importing the plugin and its gui package must not load any Qt binding."""
    code = (
        "import sys\n"
        "import chisurf.plugins.pch as p\n"
        "import chisurf.plugins.pch.gui\n"
        "assert p.name\n"
        "mods = [m for m in sys.modules if m.split('.')[0] in ('PyQt5', 'PySide2', 'qtpy')]\n"
        "assert not mods, mods\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(pathlib.Path(__file__).resolve().parents[4]),
    )
    assert result.returncode == 0, result.stderr
