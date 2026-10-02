"""Figures of the detector setup / channel definition editor (the one-page emtk editor) for the guides.

Usage (repository root, ``QT_QPA_PLATFORM=offscreen``, ``PYTHONPATH`` with the repository and emtk)::

    python docs/guides/screenshots/channel_editor_emtk.py

Writes into ``docs/guides/figures``: ``channel_definition_page.png`` (guide 87), ``channel_definition_plot.png`` (guide 87),
``lut_channel_box.png`` (guide 37) and ``image_browser_setup.png`` (guide 86). Settings, setups file and MMFDB are temporary; the
measurement is the BH SPC-132 test file.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FIG = REPO / "docs" / "guides" / "figures"
tmp = Path(tempfile.mkdtemp(prefix="guide_ce_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m" / "db.sqlite")
(tmp / "s").mkdir()
(tmp / "m").mkdir()
sample = tmp / "BH_SPC132.spc"
shutil.copy(REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc", sample)
sys.path.insert(0, str(REPO))
os.chdir(REPO)

from emtk.testing import RecordingPainter  # noqa: E402

from test.gui.emtk_port_parity import emtk_screenshot  # noqa: E402

from chisurf.plugins.core.setup_channel_definition.gui.app import make_app  # noqa: E402
from chisurf.plugins.core.setup_channel_definition.test import driver  # noqa: E402

SETUP = {
    "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
    "detectors": {
        "green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "red": {"chs": [9, 1, 2], "micro_time_ranges": [[0, 2048]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "yellow": {"chs": [9, 1, 2], "micro_time_ranges": [[2048, 4095]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
    },
    "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 13.5, "micro_time_resolution": 3.3, "micro_time_binning": 1},
}


def shot(app, name, size):
    app.pointer_move(-20.0, -20.0)
    for _ in range(4):
        app.draw(RecordingPainter(), 0.0, 0.0, *size)
    emtk_screenshot(app, FIG / name, size)
    print("wrote", name)


app = make_app(settings=SETUP, file_path=str(tmp / "setups.json"))
driver.settle(app, (1200, 800))
driver.populate(app, sample)
shot(app, "channel_definition_page.png", (1000, 640))
app.page.preview_window.show()
shot(app, "channel_definition_plot.png", (1000, 640))
app.page.preview_window.hide()
app.close()

# the LUT handling box with a LUT assigned to channel 0 and a shift on channel 8
import numpy as np  # noqa: E402

lut = dict(SETUP, apply_lut=True, channel_luts={"0": np.linspace(0, 4096, 4096).tolist()}, channel_shifts={"8": 3},
           channel_lut_sources={"0": "uniform.spc"})
app = make_app(settings=lut, file_path=str(tmp / "lut_setups.json"))
app.page.open_sections.update(reading=False, windows=False, detectors=True, lut=True)
shot(app, "lut_channel_box.png", (800, 560))
app.close()

# the Detector setup page of the image browser: the same editor in the 720 px column
from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app as image_browser  # noqa: E402

browser = image_browser()
for _ in range(3):
    browser.draw(RecordingPainter(), 0.0, 0.0, 900.0, 700.0)
p = RecordingPainter()
browser.draw(p, 0.0, 0.0, 900.0, 700.0)
x, y, w, h = next(t[:4] for t in p.texts if t[5] == "Detector setup")
browser.pointer_move(x + w / 2, y + h / 2)
browser.draw(RecordingPainter(), 0.0, 0.0, 900.0, 700.0)
browser.pointer_press(x + w / 2, y + h / 2, 1)
browser.draw(RecordingPainter(), 0.0, 0.0, 900.0, 700.0)
browser.pointer_release(x + w / 2, y + h / 2, 1)
browser.editor.load_definition(SETUP)
driver.finish_read(type("A", (), {"page": browser.editor})()) if browser.editor.read(str(sample)) is None else None
shot(browser, "image_browser_setup.png", (900, 700))
browser.close()
