"""Capture every consumer of the shared editor showing the one-page editor, populated (BH SPC-132 read), on TEMPORARY settings.

Usage: python capture_consumers.py <out_dir>   (repository root, QT_QPA_PLATFORM=offscreen, PYTHONPATH with the repository
and emtk). Writes consumer_<name>_<w>x<h>.png: tttr_image_browser (setup page, the 720 px column), boarding (detector
step), bid_to_analysis (the 43 % column of the burst pipeline), burst_background, burst_irf_bg, accurate_fret,
tttr_count_rate_analysis (its 290 px dock), trace_browser (setup page), audifier, microtime_histogram.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

out = Path(sys.argv[1]).resolve()
tmp = Path(tempfile.mkdtemp(prefix="ce_cons_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m" / "db.sqlite")
(tmp / "s").mkdir()
(tmp / "m").mkdir()
sample = tmp / "BH_SPC132.spc"
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", sample)
os.chdir(tmp)

from emtk.testing import RecordingPainter  # noqa: E402

from test.gui.emtk_port_parity import emtk_screenshot  # noqa: E402

from chisurf.plugins.core.setup_channel_definition.test import driver  # noqa: E402

DEFAULTS = {
    "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
    "detectors": {
        "green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "red": {"chs": [9, 1, 2], "micro_time_ranges": [[0, 2048]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
    },
    "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 13.5, "micro_time_resolution": 3.3, "micro_time_binning": 1},
}


def settle(app, size, n=4):
    for _ in range(n):
        app.draw(RecordingPainter(), 0.0, 0.0, *size)


def shot(app, name, size):
    app.pointer_move(-20.0, -20.0)
    settle(app, size)
    emtk_screenshot(app, out / f"consumer_{name}_{size[0]}x{size[1]}.png", size)
    print("wrote", f"consumer_{name}_{size[0]}x{size[1]}.png")


def click(app, text, size, nth=0):
    p = RecordingPainter()
    app.draw(p, 0.0, 0.0, *size)
    hits = [t for t in p.texts if t[5] == text]
    x, y, w, h = hits[nth][:4]
    app.pointer_move(x + w / 2, y + h / 2)
    app.draw(RecordingPainter(), 0.0, 0.0, *size)
    app.pointer_press(x + w / 2, y + h / 2, 1)
    app.draw(RecordingPainter(), 0.0, 0.0, *size)
    app.pointer_release(x + w / 2, y + h / 2, 1)
    settle(app, size)


def read(editor):
    editor.read(str(sample))
    driver.finish_read(type("A", (), {"page": editor})())


# tttr_image_browser: setup page, the editor is drawn at most 720 px wide
from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app as image_browser  # noqa: E402

for size in ((1200, 800), (800, 600)):
    app = image_browser()
    settle(app, size)
    click(app, "Detector setup", size)
    app.editor.load_definition(DEFAULTS)
    read(app.editor)
    shot(app, "tttr_image_browser", size)
    app.close()

# boarding: the detector step
from chisurf.plugins.core.boarding.app import BoardingApp  # noqa: E402
from chisurf.plugins.core.boarding.model import STEPS  # noqa: E402

for size in ((1200, 800), (800, 600)):
    app = BoardingApp()
    index = next(i for i, s in enumerate(STEPS) if s.id == "detector")
    app.model.go_to(index)
    settle(app, size)
    shot(app, "boarding_detector_step", size)
    app.close()

# bid_to_analysis: the setup is a 43 % column
from chisurf.plugins.burst.bid_to_analysis.gui.app import create_app as bid  # noqa: E402

for size in ((1200, 800), (800, 600)):
    app = bid()
    settle(app, size)
    app.setup.load_definition(DEFAULTS)
    read(app.setup)
    shot(app, "bid_to_analysis", size)
    app.close()

# burst_background / burst_irf_bg / accurate_fret / count rate: the editor in a dock tab or column
from chisurf.plugins.burst.burst_background.gui.app import create_app as background  # noqa: E402

app = background()
settle(app, (1200, 800))
shot(app, "burst_background", (1200, 800))
app.close()

from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app as irf  # noqa: E402

app = irf()
settle(app, (1200, 800))
click(app, "Channel definition", (1200, 800))
shot(app, "burst_irf_bg_channel_definition", (1200, 800))
app.close()

from chisurf.plugins.burst.accurate_fret.gui.app import create_app as fret  # noqa: E402

app = fret()
settle(app, (1200, 800))
shot(app, "accurate_fret", (1200, 800))
app.close()

from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app as rates  # noqa: E402

app = rates()
settle(app, (1200, 800))
shot(app, "tttr_count_rate_analysis", (1200, 800))
app.close()

from chisurf.plugins.tttr.trace_browser.gui.app import TraceBrowserApp  # noqa: E402

app = TraceBrowserApp(setups_file=str(tmp / "trace_setups.json"))
app.back_to_setup()
settle(app, (1200, 800))
shot(app, "trace_browser_setup", (1200, 800))
app.close()

from chisurf.plugins.tttr.audifier.gui.app import create_app as audifier  # noqa: E402

app = audifier()
settle(app, (1200, 800))
shot(app, "audifier", (1200, 800))
app.close()

from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app as microtime  # noqa: E402

app = microtime()
settle(app, (1200, 800))
shot(app, "microtime_histogram", (1200, 800))
app.close()
