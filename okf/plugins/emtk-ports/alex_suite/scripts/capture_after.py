"""After-evidence of the native ALEX hub: every step, populated by the demo walk, at 1200x800 and 800x600.

Walks the simulated µs-ALEX measurement (``alex_suite/demo.py``) with the files step's Load demo data and Next
presses only, exactly as the tour does, then opens each side tool. Per step it writes
``after_steps/after_<role>_<w>x<h>.png`` and records what the hub draws there
(``test.gui.emtk_port_parity.emtk_inventory``); ``after.json`` is the union, with the Qt-free check, so
``python -m test.gui.emtk_port_parity compare alex_suite --out okf/plugins/emtk-ports/alex_suite`` compares it with
the per-step Qt baseline of ``capture_before.py``. Also writes ``docs/guides/figures/alex_suite_hub.png`` (the
E-S step, 1200x800) for the guide. Temporary settings; nothing touches ``~/.chisurf``.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:. \
        python okf/plugins/emtk-ports/alex_suite/scripts/capture_after.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
OUT = REPO / "okf" / "plugins" / "emtk-ports" / "alex_suite"
STEPS_DIR = OUT / "after_steps"
FIGURE = REPO / "docs" / "guides" / "figures" / "alex_suite_hub.png"
sys.path.insert(0, str(REPO))
sys.modules.pop("test", None)

tmp = Path(tempfile.mkdtemp(prefix="alex_after_"))
for key in ("CHISURF_SETTINGS_DIR", "MMFDB_SETTINGS_DIR", "NDXPLORER_SETTINGS_DIR"):
    (tmp / key).mkdir()
    os.environ[key] = str(tmp / key)
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "mmfdb.sqlite")

from test.gui.emtk_port_parity import emtk_inventory, normalize, qt_free  # noqa: E402  (before chisurf: see below)

from emtk import testing  # noqa: E402

from chisurf.plugins.burst.alex_suite.gui.native import create_app  # noqa: E402
from chisurf.plugins.emtk_test_input import Driver  # noqa: E402

# (a chisurf import pulls in the standard library's ``test`` package, after which ``test.gui`` no longer resolves)

STEPS_DIR.mkdir(exist_ok=True)
hub = create_app()
drv = Driver(hub, (1200, 800))
controls: set[str] = set()
untooltipped: set[str] = set()
per_step: dict[str, list[str]] = {}


def settle(timeout=240.0):
    end = time.monotonic() + timeout
    drv.draw(2)
    while (hub._busy() or hub._pending_next) and time.monotonic() < end:
        time.sleep(0.05)
        drv.draw(1)
    drv.draw(2)


def wait_for(condition, timeout=60.0):
    end = time.monotonic() + timeout
    while not condition() and time.monotonic() < end:
        time.sleep(0.05)
        drv.draw(1)
    drv.draw(2)


def capture(role: str) -> None:
    """Both sizes (pointer parked off the controls, so no tooltip covers them), then the inventory."""
    hub.pointer_move(5.0, 795.0)
    for size in ((800, 600), (1200, 800)):
        painter = None
        for _ in range(4):
            painter = testing.PixelPainter(*size)
            hub.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
        path = STEPS_DIR / f"after_{role}_{size[0]}x{size[1]}.png"
        path.write_bytes(testing.png_encode(painter.width, painter.height, painter.px))
    inventory = emtk_inventory(hub, (1200, 800))
    per_step[role] = inventory["controls"]
    controls.update(inventory["controls"])
    untooltipped.update(inventory["controls_without_tooltip"])
    drv.draw(2)


def press_next():
    drv.click(hub.item_rects["next"])
    settle()


# every step empty first (the Qt baseline was taken empty too), then the walk
drv.draw(3)
for panel in list(hub.tools):
    hub.select(panel["role"])
    settle()
    capture(panel["role"] + "_empty")
hub.close()
hub = create_app()
drv = Driver(hub, (1200, 800))
drv.draw(3)
capture("setup")
press_next()
drv.click(hub._target_rect("demo"))
drv.draw(2)
capture("data")
press_next()
wait_for(lambda: not hub.children["alternation"].model.running)
capture("alternation")
press_next()
capture("selection_ready")
press_next()
capture("selection")  # not the open step any more: shown again below with its result
wait_for(lambda: bool(hub.children["background"].model.diagnostics))
capture("background")
press_next()
wait_for(lambda: not hub.children["accurate_fret"].controller.running)
capture("accurate_fret_loaded")
press_next()
es = hub.children["es"]
wait_for(lambda: es.model.has_data)
capture("es")
if FIGURE.parent.is_dir():
    hub.pointer_move(5.0, 795.0)
    for _ in range(4):
        painter = testing.PixelPainter(1200, 800)
        hub.draw(painter, 0.0, 0.0, 1200.0, 800.0)
    FIGURE.write_bytes(testing.png_encode(painter.width, painter.height, painter.px))
for role in ("selection", "accurate_fret", "browser", "titration", "bva", "legacy_export"):
    hub.select(role)
    settle()
    if role == "browser":
        wait_for(lambda: hub.children["browser"].model.table is not None)
    capture(role)
# the tour's first await step, as a user sees it
hub.select("setup")
settle()
hub.tour.start()
hub.tour.step_idx = 2
drv.draw(3)
capture("guide_next")
hub.tour.active = False
# the help window
hub.help.show()
capture("help")
hub.close()

after = {
    "entrypoint": "chisurf.plugins.burst.alex_suite.gui.native:make_app (every step, populated by the demo walk)",
    "size": [1200, 800],
    "controls": sorted({normalize(c) for c in controls} - {""}),
    "per_step": per_step,
    "controls_without_tooltip": sorted(untooltipped),
    "qt_free": qt_free("alex_suite"),
}
(OUT / "after.json").write_text(json.dumps(after, indent=2, ensure_ascii=False))
print("after controls", len(after["controls"]), "untooltipped", after["controls_without_tooltip"],
      "qt_free", after["qt_free"].get("ok"))
