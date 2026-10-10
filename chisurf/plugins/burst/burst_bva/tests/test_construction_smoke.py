"""Construction smoke test for the native BVA app and the headless import boundary.

The plugin package imports without a Qt binding (``api`` / ``core`` / ``backend`` / ``cli``), and the
native app builds and draws an empty frame.
"""

from __future__ import annotations

import subprocess
import sys


def test_app_constructs_and_draws_empty() -> None:
    """The emtk app builds with no data and paints one frame."""
    from emtk.testing import RecordingPainter

    from chisurf.plugins.burst.burst_bva.gui.app import create_app

    app = create_app()
    try:
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1000, 700)
        assert painter.strings
    finally:
        app.close()


def test_package_root_imports_without_qt() -> None:
    """Importing the plugin root must not pull in Qt."""
    code = (
        "import sys\n"
        "import chisurf.plugins.burst.burst_bva as p\n"
        "assert p.name\n"
        "mods = [m for m in sys.modules if m.split('.')[0] in ('qtpy', 'PyQt5', 'PySide2')]\n"
        "assert not mods, mods[:5]\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
