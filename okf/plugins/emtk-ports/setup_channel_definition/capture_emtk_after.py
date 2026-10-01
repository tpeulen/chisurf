"""Capture the emtk tool in every state the report discusses, on TEMPORARY settings and MMFDB.

Usage: python capture_emtk_after.py <out_dir>   (repository root, QT_QPA_PLATFORM=offscreen,
PYTHONPATH with the repository and emtk). Writes after_tab_<name>_<size>.png for the six tabs at
1200x800 and 800x600, the empty state, a saved/public setup, a calibration snapshot, the three
prompts, the help window and a guide step.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

out = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="scd_after_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m" / "db.sqlite")
(tmp / "s").mkdir()
(tmp / "m").mkdir()
sample = tmp / "BH_SPC132.spc"
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", sample)

from test.gui.emtk_port_parity import emtk_screenshot  # noqa: E402  (before anything shadows `test`)

from mmfdb.repository import MFDatabase  # noqa: E402

from chisurf.core.fio import setup_store  # noqa: E402
from chisurf.plugins.core.setup_channel_definition.gui.app import make_app  # noqa: E402
from chisurf.plugins.core.setup_channel_definition.test import driver  # noqa: E402

user = setup_store.resolve_active_user_id()
db = MFDatabase(str(tmp / "m" / "db.sqlite"))
db.ensure_user(user)
db.conn.commit()

SIZES = [(1200, 800), (800, 600)]


def shot(app, name, size):
    app.pointer_move(-20.0, -20.0)  # no hover tooltip in the picture
    driver.settle(app, size, 2)
    path = out / f"{name}_{size[0]}x{size[1]}.png"
    emtk_screenshot(app, path, size)
    print("wrote", path.name)


app = make_app(db=db)
for size in SIZES:
    driver.settle(app, size)
    shot(app, "after_empty", size)

driver.populate(app, sample)
for size in SIZES:
    for tab in driver.TAB_NAMES:
        driver.select_tab(app, tab, size)
        shot(app, f"after_tab_{tab.lower().replace(' ', '_')}", size)

# the state a user reaches: a setup saved, public, with a calibration snapshot applied
driver.select_tab(app, "Detectors")
app.toolbar.save("Lab setup A")
app.toolbar.select_public(True)
app.toolbar.save("Lab setup A")
key = setup_store.setup_id_for_name("Lab setup A", user, "tttr_detector_setup")
for channel, (g, l1, l2) in driver.CAL.items():
    db.add_setup_calibration(key, channel, g_factor=g, l1=l1, l2=l2, calibrated_at=driver.STAMP, method="manual", created_by_user_id=user)
db.conn.commit()
app.toolbar.select("Lab setup A")
app.toolbar.select_calibration(driver.STAMP)
driver.select_tab(app, "Detectors")
shot(app, "after_populated_saved_calibration", (1200, 800))
shot(app, "after_populated_saved_calibration", (800, 600))

for kind, setup in (("save", lambda b: b.request_save()), ("rename", lambda b: b.request_rename()), ("delete", lambda b: b.request_delete())):
    setup(app.toolbar)
    for size in reversed(SIZES):  # a dialog keeps the position it was first drawn at
        driver.settle(app, size)
        shot(app, f"after_populated_prompt_{kind}", size)
    app.toolbar.cancel()
    driver.settle(app)

app.toolbar.save("Lab setup B")
app.toolbar.select("Lab setup B")
app.toolbar.request_rename()
app.toolbar.name_text = "Lab setup A"
app.toolbar.confirm()
driver.settle(app)
shot(app, "after_populated_prompt_overwrite", (1200, 800))
app.toolbar.cancel()

app.toolbar.select("")
app.toolbar.request_rename()  # nothing selected: the status line says so
driver.select_tab(app, "Setups")
shot(app, "after_populated_no_selection", (1200, 800))

driver.click_text(app, "Help")
driver.settle(app)
shot(app, "after_populated_help", (1200, 800))
app.help_window.open = False
app.help_window.dlg.hide()
app.tour.start(2)
driver.settle(app)
shot(app, "after_populated_guide", (1200, 800))
app.tour.stop()
narrow = (520, 500)
driver.settle(app, narrow)
shot(app, "after_populated_narrow", narrow)
