"""The views rearranged by a real drag: 3D View dragged onto the right pad, beside Positions. usage: capture_split.py <out_dir>

Writes after_split_3dview_<W>x<H>.png. The Qt editor's views were dock widgets; the native ones are dock windows.
"""
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fixtures  # noqa: E402

out = pathlib.Path(sys.argv[1])
work = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(work / "s"), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
from test.gui import emtk_port_parity as epp  # noqa: E402, I001
from chisurf.plugins.modelling.fps_json_editor.gui.app import make_app  # noqa: E402
from chisurf.plugins.modelling.fps_json_editor.test.test_emtk_real_input import _drag_tab_to_right_pad  # noqa: E402
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui  # noqa: E402

for size in ((1200, 800), (800, 600)):
    app = make_app()
    fps, _ = fixtures.make(work)
    app.load_path(str(fps))
    ed = app.editor
    ed.compute_all()
    t0 = time.time()
    while ed.busy and time.time() - t0 < 300:
        ed.poll()
        time.sleep(0.1)
    ed.poll()
    ui = Ui(app, size)
    _drag_tab_to_right_pad(ui, "3D View")
    print(size, app.docks.selected)
    app.pointer_move(size[0] * 0.25, size[1] - 12)  # off the 3D view, so no tooltip covers it
    for _ in range(5):
        ui.draw(1)
    epp.emtk_screenshot(app, out / f"after_split_3dview_{size[0]}x{size[1]}.png", size)
    app.close()
