"""Qt before-images of the legacy ALEX Suite shell (``AlexSuiteTool``), one per step, and the control inventory.

The Qt shell's rail and every step panel are emtk surfaces hosted in Qt (``ControlHost``), so a Qt
``findChildren`` inventory sees nothing (the 2026-10-03 ``before.json`` has 0 controls). This walks every role,
grabs the window, and records what the shell's own emtk app and each hosted step app draw
(``test.gui.emtk_port_parity.emtk_inventory``). Run on temporary settings with the ALEX setup the alternation step
writes saved and selected (what a µs-ALEX user sees after step 3).

    QT_QPA_PLATFORM=offscreen PYTHONPATH=modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:. \
        python okf/plugins/emtk-ports/alex_suite/scripts/capture_before.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
OUT = REPO / "okf" / "plugins" / "emtk-ports" / "alex_suite"
sys.path.insert(0, str(REPO))
sys.modules.pop("test", None)

tmp = Path(tempfile.mkdtemp(prefix="alex_before_"))
for key in ("CHISURF_SETTINGS_DIR", "MMFDB_SETTINGS_DIR"):
    (tmp / key).mkdir()
    os.environ[key] = str(tmp / key)
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "mmfdb.sqlite")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtWidgets  # noqa: E402

from test.gui.emtk_port_parity import emtk_inventory, normalize  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from chisurf.plugins.burst.alex_suite.gui.alternation import build_setup  # noqa: E402
from chisurf.plugins.burst.burst_selection.gui.model import save_setup  # noqa: E402

save_setup("ALEX Suite (auto)", build_setup({"green": (616, 3784), "red": (4278, 7762)}, [1], [0], 8000))

from emtk.qt_host import ControlHost  # noqa: E402,F401

from chisurf.plugins.burst.alex_suite.gui.tool import ALEX_PANELS, AlexSuiteTool  # noqa: E402

tool = AlexSuiteTool()
tool.resize(1200, 800)
tool.show()
for _ in range(30):
    app.processEvents()

controls: set[str] = set()
per_step: dict[str, list[str]] = {}
untooltipped: set[str] = set()


def _hosted_apps(widget):
    found = []
    for child in [widget, *widget.findChildren(QtWidgets.QWidget)]:
        control = getattr(child, "control", None)
        if control is not None and hasattr(control, "draw") and control not in found:
            found.append(control)
    return found


for panel in ALEX_PANELS:
    if panel.get("separator"):
        continue
    role = panel["role"]
    tool.show_panel_by_role(role)
    for _ in range(40):
        app.processEvents()
    tool.grab().save(str(OUT / "before_steps" / f"before_{role}_1200x800.png"))
    seen: set[str] = set()
    widget = tool._workflow_panels.get(role)
    apps = [tool.app] + (_hosted_apps(widget) if widget is not None else [])
    for hosted in apps:
        try:
            inv = emtk_inventory(hosted, (970, 700) if hosted is not tool.app else (1200, 800))
        except Exception as exc:  # noqa: BLE001 - recorded, the image still shows the step
            seen.add(f"<inventory failed: {type(exc).__name__}: {exc}>")
            continue
        seen |= set(inv["controls"])
        untooltipped |= set(inv["controls_without_tooltip"])
    per_step[role] = sorted(seen)
    controls |= seen
    print(role, len(seen))

tool.close()
before = {
    "entrypoint": "chisurf.plugins.burst.alex_suite.gui.tool:AlexSuiteTool (shell app + every hosted step app)",
    "size": [1200, 800],
    "controls": sorted({normalize(c) for c in controls} - {""}),
    "per_step": per_step,
    "controls_without_tooltip": sorted(untooltipped),
}
(OUT / "before.json").write_text(json.dumps(before, indent=2, ensure_ascii=False))
print("before controls", len(before["controls"]))
