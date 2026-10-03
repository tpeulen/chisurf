"""Capture the legacy Qt Settings hub (every destination) on TEMPORARY settings. Usage: <out_dir>.

Run from the repository root with QT_QPA_PLATFORM=offscreen and PYTHONPATH="$PWD:$HOME/dev/emtk". Settings, MMFDB and HOME
are in a temp folder; the updater's fakes stand in for network and conda.
"""
import json, sys, tempfile, time
from pathlib import Path

import pytest

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp(prefix="setup_qt_"))
mp = pytest.MonkeyPatch()
from chisurf.plugins.core.setup.test import seeded
seeded.prepare(tmp, mp)

from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.core.setup.gui.tool import UnifiedSettingsTool

w = UnifiedSettingsTool()
info = {}


def pump(ms=0.3):
    end = time.monotonic() + ms
    while time.monotonic() < end:
        app.processEvents()


for size in ((1200, 800), (800, 600)):
    w.resize(*size); w.show(); pump(0.5)
    info[f"actual_{size[0]}"] = [w.width(), w.height()]
    rows = [(i, w.nav_list.item(i).text()) for i in range(w.nav_list.count())]
    info["rows"] = rows
    for i, text in rows:
        w.nav_list.setCurrentRow(i); pump(1.0)
        name = "".join(c if c.isalnum() else "_" for c in text.split(" ", 1)[-1]).lower()
        w.grab().save(str(out / f"before_populated_{i:02d}_{name}_{size[0]}x{size[1]}.png"))
        print("wrote", i, text)
w.nav_list.setCurrentRow(0)
info["next_enabled"] = w._btn_next.isEnabled(); info["prev_enabled"] = w._btn_prev.isEnabled()
info["status"] = w._status_message.text()
w._on_search_changed("plug"); info["search_plug"] = [w.nav_list.item(i).text() for i in range(w.nav_list.count()) if not w.nav_list.item(i).isHidden()]
w._on_search_changed("")
w.goto_next_step(); w.goto_next_step(); info["after_two_next"] = w.nav_list.currentRow()
w.goto_prev_step(); info["after_back"] = w.nav_list.currentRow()
(out / "before_populated.json").write_text(json.dumps(info, indent=2, ensure_ascii=False))
print(json.dumps(info, ensure_ascii=False))
