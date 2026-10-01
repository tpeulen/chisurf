"""Populated captures on the demo burst folder (60 bursts, static and dynamic), FRET-2CDE computed.

usage: capture_populated.py <out_dir> qt|emtk <prefix> [<qt_head dir>]   (run from the repo root)
qt = the committed Qt tool (HEAD sources via qt_head, overlaying app and view_model).
"""
import pathlib, sys, tempfile

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
from test.gui.emtk_port_parity import emtk_screenshot  # before the burst modules: another `test` package shadows it
from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build
from chisurf.plugins.burst.burst_bva.core import computation as bva
from chisurf.plugins.burst.burst_2cde.core import computation as core

folder = build(pathlib.Path(tempfile.mkdtemp()) / "measurement")


def result():
    df, tttrs = bva.read_burst_analysis(folder, "SPC-130", pattern="bi4_bur")
    return core.compute_2cde(df, tttrs, donor_channels=[0], acceptor_channels=[1], donor_micro_time_ranges=[],
                             acceptor_micro_time_ranges=[], tau=100e-6, kernel="laplace", variant="fret")


if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("burst_2cde", ("app", "view_model"))
    w = klass()
    w.model.set_folder(folder)
    w.model.donor_channels_text, w.model.acceptor_channels_text = "0", "1"
    w.model.set_result(result(), "fret")
    w.resize(1200, 800); w.show()
    for _ in range(30):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.burst.burst_2cde.gui.app import create_app
    df = result()
    for size in [(1200, 800), (800, 600)]:
        a = create_app()
        a.model.set_folder(folder)
        a.model.donor_channels_text, a.model.acceptor_channels_text = "0", "1"
        a.model.set_result(df, "fret")
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        a.close()
