"""A fit window's right-click *Export image…* / *Export data as CSV…* write the panel, without Qt.

The menu called the Qt wrapper's ``_on_export_image`` / ``_on_export_csv`` (a Qt file
dialog), which a toolkit-free :class:`chisurf.chiplot.Panel` does not have: since the
pages moved onto the chiplot core the two entries raised ``AttributeError``. They now ask
with emtk's save dialog and write through the panel's own exporters (the image on emtk's
CPU rasteriser). Run in a fresh interpreter, so Qt staying unloaded is measured.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_the_panel_menu_exports_write_files_without_qt(tmp_path):
    code = textwrap.dedent(
        f"""
        import sys
        import numpy as np
        from emtk.export import grab
        from chisurf import chiplot as cp
        from chisurf.emtk.fit_pages.surface import make_surface

        panel = cp.Panel(title="decay")
        panel.line(np.arange(40.0), np.exp(-np.arange(40.0) / 7.0) * 1e3, pen="orange", name="d")
        surface = make_surface()
        surface.add_page("decay", "Decay", lambda: None)
        for kind, name in (("image", "panel.png"), ("csv", "panel.csv")):
            surface.ask_export(kind, panel)
            dialog = surface._export[2]
            dialog.draw = lambda name=name: [{str(tmp_path)!r} + "/" + name]
            grab(surface, (900, 600), frames=2)
            assert surface._export is None, "the dialog closes once a path is chosen"
        print(sorted(m for m in ("qtpy", "PyQt5") if m in sys.modules))
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=300
    )
    assert out.returncode == 0, out.stderr[-3000:]
    assert out.stdout.strip().splitlines()[-1] == "[]", out.stdout
    assert (tmp_path / "panel.png").stat().st_size > 0
    header = (tmp_path / "panel.csv").read_text().splitlines()[0]
    assert header == "d x,d y"
