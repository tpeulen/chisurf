"""ChiSurf opens ndX only as the emtk app: nothing reaches the old Qt window.

ndX's Qt window (``ndxplorer.core.plot_main.NDXplorer``, its ``ui`` /
``widgets`` packages and the pyqtgraph plotting modules) was deleted from
ndXplorer; the emtk app is its only GUI. Every route in ChiSurf goes through
:func:`chisurf.plugins.ndxplorer.window.build_ndxplorer_window`, which hosts the
emtk app. An import of one of the deleted modules would fail at run time,
usually inside a ``try`` that turns it into a silently dead button, so it fails
here instead.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
PACKAGE = ROOT / "chisurf"

#: The Qt window and its deleted modules, by module or by class, however spelled.
QT_WINDOW = re.compile(
    r"ndxplorer\.core\.plot_main"
    r"|from\s+ndxplorer(?:\.core)?\s+import\s+[^\n]*\bNDXplorer\b"
    r"|\bndxplorer\.NDXplorer\b"
    r"|\bmake_ndxplorer\b"
    r"|\bndxplorer\.(?:ui|widgets|report_tool|settings_helpers|deps_installer"
    r"|phasor_integration|plugins)\b"
    r"|\bndxplorer\.analysis\.(?:send_menu|clustering|clustering_helpers|gaussian_fit"
    r"|umap_helpers|umap_progress)\b"
    r"|\bndxplorer\.plotting\.(?:curve_overlay|pg_image_widget|plot_control|plot_helpers"
    r"|plot_umap|image_items|colormaps|histograms|plot_update_helpers|api|scatter)\b"
    r"|\bndxplorer\.io\.(?:file_operations|file_open_helpers|async_loader)\b"
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
    assert not offenders, "the deleted Qt ndX window is used:\n" + "\n".join(offenders)
