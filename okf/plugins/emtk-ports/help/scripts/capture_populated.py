"""Populated captures: Qt HelpWidget (as committed) and the emtk HelpApp on the same page."""
import importlib.util, pathlib, subprocess, sys, tempfile
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
page = pathlib.Path("docs/concepts/fret.md").resolve()
if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import chisurf.plugins.core.help.gui as pkg
    src = subprocess.run(["git", "show", "HEAD:chisurf/plugins/core/help/gui/tool.py"], capture_output=True, text=True, check=True).stdout
    tmp = pathlib.Path(tempfile.mkdtemp()) / "_head_tool.py"; tmp.write_text(src)
    s = importlib.util.spec_from_file_location("chisurf.plugins.core.help.gui._head_tool", tmp)
    m = importlib.util.module_from_spec(s); sys.modules[s.name] = m; s.loader.exec_module(m)
    w = m.HelpWidget(); w.resize(1200, 800); w.show()
    for _ in range(20): app.processEvents()
    w.navigate(page)
    for _ in range(20): app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
else:
    from chisurf.plugins.core.help.gui.help_app import make_help_app
    for size in [(1200, 800), (800, 600)]:
        a = make_help_app()
        for _ in range(2): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_home_{size[0]}x{size[1]}.png", size)
        a.model.open_page(page)
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_page_{size[0]}x{size[1]}.png", size)
        a.close()
