"""Drive the emtk LUT Tools app into the states of the evidence screenshots.

Usage: python emtk_populated.py <tempdir with BH_SPC132.spc> <out dir>
Everything runs on temporary settings; the sample is a private copy.
"""
import os
import pathlib
import sys
import time

sys.path.insert(0, os.getcwd())  # run from the repository root
T = pathlib.Path(sys.argv[1])
O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot  # first: emtk.testing shadows `test`
from emtk.testing import RecordingPainter

from chisurf.plugins.tttr.tttr_lut_tools.gui.app import create_app

app = create_app(preferences_path=T / "prefs_evidence.json")
m = app.model


def settle(size=(1200, 800)):
    for _ in range(300):
        app.draw(RecordingPainter(), 0, 0, *size)
        if not app.job.busy and not m.job_request:
            return
        time.sleep(0.02)


def shot(name, size):
    emtk_screenshot(app, O / f"{name}_{size[0]}x{size[1]}.png", size)


SIZES = ((1200, 800), (800, 600))
for size in SIZES:
    shot("after_empty", size)
m.add_files([str(T / "BH_SPC132.spc")])
settle()
c = m.ws.compute
for size in SIZES:
    shot("after_populated_loaded", size)
c.linear_start, c.linear_stop = 1200, 1900  # the region the Qt baseline picked
m.param_changed()
for size in SIZES:
    shot("after_populated", size)
m.message = ""
m.autodetect()  # channel 0 has no plateau: the failure is reported
shot("after_populated_autodetect_failed", SIZES[0])
m.channel = "8"
m.channel_changed()
c.linear_start, c.linear_stop = 1200, 1900
m.param_changed()
m.autodetect()
shot("after_populated_autodetect_ch8", SIZES[0])
m.channel = "0"
m.channel_changed()
c.linear_start, c.linear_stop = 1200, 1900
m.param_changed()
app.form.folds["Advanced"] = True
m.message = ""
shot("after_populated_advanced", SIZES[0])
app.form.folds["Advanced"] = False
m.add_all()
settle()
shot("after_populated_added", SIZES[0])
m.stage = 1
m.add_files([str(T / "BH_SPC132.spc")])
settle()
m.ws.active_channel = 0
m.show_lut = True
for size in SIZES:
    shot("after_populated_tab2", size)
m.show_json = True
shot("after_populated_tab2_json", SIZES[0])
m.show_json = False

m.request_save_lut()
m.stage = 0
shot("after_populated_file_dialog", SIZES[0])
app.dialog = None
app.help_window.show()
shot("after_populated_help", SIZES[0])
app.help_window.hide()
shot("after_populated_narrow", (500, 500))
app.tour.start(0)
shot("after_populated_guide", SIZES[0])
