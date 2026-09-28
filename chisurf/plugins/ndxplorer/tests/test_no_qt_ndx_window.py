"""ChiSurf opens ndX only as the emtk app: nothing reaches the legacy Qt window.

ndX's Qt window (``ndxplorer.core.plot_main.NDXplorer``) is legacy; every route
in ChiSurf goes through
:func:`chisurf.plugins.ndxplorer.window.build_ndxplorer_window`, which hosts the
emtk app. A new import of the Qt window would bring back a second ndX with a
different set of features, so it fails here.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
PACKAGE = ROOT / "chisurf"

#: The Qt window, by module or by class, however it is spelled.
QT_WINDOW = re.compile(
    r"ndxplorer\.core\.plot_main"
    r"|from\s+ndxplorer(?:\.core)?\s+import\s+[^\n]*\bNDXplorer\b"
    r"|\bndxplorer\.NDXplorer\b"
    r"|\bmake_ndxplorer\b"
)


def test_no_chisurf_module_opens_the_qt_ndx_window():
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path == pathlib.Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if QT_WINDOW.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert not offenders, "the legacy Qt ndX window is used:\n" + "\n".join(offenders)
