"""Draw the emtk wizard through every step, populated, and write the evidence.

Usage: ``python capture_after_steps.py <out_dir>`` from the repository root with
QT_QPA_PLATFORM=offscreen and PYTHONPATH="$PWD:$HOME/dev/emtk". Settings, metadata database and
the detector / FCS stores live in a temporary folder; nothing touches ``~/.chisurf``, the
keyring or the network.

Writes ``after_step<N>_<id>_<w>x<h>.png`` for every step at both sizes, the populated and dialog
states, and merges the control inventory of every state (``test.gui.emtk_port_parity``'s own
``emtk_inventory``) into ``after.json``: the stock ``after`` command draws only the first
step, while this app shows one step at a time.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

out = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="boarding_after_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "cs")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "mm")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "mm" / "m.db")

from emtk.testing import RecordingPainter  # noqa: E402

from test.gui.emtk_port_parity import SIZES, emtk_inventory, emtk_screenshot  # noqa: E402

from chisurf.emtk.i18n import install  # noqa: E402
from chisurf.plugins.core.boarding.app import BoardingApp  # noqa: E402
from chisurf.plugins.core.boarding.model import STEPS  # noqa: E402

install()
app = BoardingApp()
inventories = []


def frames(size=(1200, 800), n=3):
    for _ in range(n):
        app.draw(RecordingPainter(), 0.0, 0.0, float(size[0]), float(size[1]))


def click(label, size=(1200, 800), nth=0):
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
    hits = [t for t in painter.texts if t[5] == label]
    if len(hits) <= nth:
        return False
    x, y, w, h = hits[nth][:4]
    x, y = x + w / 2.0, y + h / 2.0
    app.pointer_move(x, y)
    frames(size, 1)
    app.pointer_press(x, y, 1)
    frames(size, 1)
    app.pointer_release(x, y, 1)
    frames(size, 2)
    return True


def shot(name):
    for size in SIZES:
        emtk_screenshot(app, out / f"after_{name}_{size[0]}x{size[1]}.png", size)
    inventories.append(emtk_inventory(app, SIZES[0]))


# empty state: the temporary folder has no settings files, no setups
for index, step in enumerate(STEPS):
    app.model.go_to(index)
    shot(f"empty_step{index + 1}_{step.id}")

# populated: files created, a detector setup and an FCS preset saved
app.model.go_to(2)
app.model.create_missing()
app.model.go_to(3)
app.model.update_experiments()
app.model.go_to(5)
frames()
editor = app.detector_editor()
for tab in ("TTTR reading", "Detectors", "PIE windows", "TAC corrections", "Optical setup", "Setups"):
    click(tab)
    shot(f"tab_{tab.lower().replace(' ', '_')}")
editor.toolbar.save("lab")
app.model.refresh_completion()
editor.toolbar.select("lab")
shot("populated_step6_detector_saved")
app.model.go_to(6)
frames()
fcs = app.fcs_editor()
fcs.model.reload_setups()
fcs.select_setup("lab")
fcs.channel_a, fcs.channel_b = "green", "red"
fcs.add_pair()
fcs.channel_a, fcs.channel_b = "green", "green"
fcs.add_pair()
fcs.save()
app.model.refresh_completion()
shot("populated_step7_fcs_saved")
app.model.go_to(1)
shot("populated_step2_settings")
app.model.go_to(4)
shot("populated_step5_dependencies")
app.model.go_to(2)
app.model.request_restore()
shot("dialog_restore_defaults")
app.model.confirm_no()
app.model.go_to(2)
shot("populated_step3_after_actions")
app.model.go_to(7)
app.model.open_help()
shot("populated_step8_finish_notice")
app.model.go_to(0)
shot("populated_step1_welcome")
emtk_screenshot(app, out / "after_populated_narrow_520x500.png", (520, 500))
app.model.go_to(5)
emtk_screenshot(app, out / "after_populated_narrow_detector_520x500.png", (520, 500))

merged = {"size": [1200, 800], "controls": set(), "interactive": [], "controls_without_tooltip": set()}
seen = set()
for inv in inventories:
    merged["controls"].update(inv["controls"])
    merged["controls_without_tooltip"].update(inv["controls_without_tooltip"])
    for row in inv["interactive"]:
        key = json.dumps(row, sort_keys=True)
        if key not in seen:
            seen.add(key)
            merged["interactive"].append(row)
previous = json.loads((out / "after.json").read_text()) if (out / "after.json").exists() else {}
merged["controls"] = sorted(merged["controls"])
merged["controls_without_tooltip"] = sorted(merged["controls_without_tooltip"])
merged["qt_free"] = previous.get("qt_free", {})
merged["states_merged"] = len(inventories)
(out / "after.json").write_text(json.dumps(merged, indent=2, ensure_ascii=False))
app.close()
print("controls:", len(merged["controls"]), "untooltipped:", merged["controls_without_tooltip"])
