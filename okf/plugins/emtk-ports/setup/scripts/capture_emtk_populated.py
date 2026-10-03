"""Capture the emtk Settings hub, every destination at 1200x800 and 800x600, populated, on TEMPORARY settings.

Usage: <out_dir> [prefix]. Same seed as the Qt capture (chisurf/plugins/core/setup/test/seeded.py): temp settings, temp
MMFDB with users, temp HOME, updater fakes (no network, no conda).
"""
import sys, tempfile, json, os
sys.path.insert(0, os.getcwd())
from pathlib import Path

import pytest

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
prefix = sys.argv[2] if len(sys.argv) > 2 else "after_populated"
only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
tmp = Path(tempfile.mkdtemp(prefix="setup_emtk_"))
mp = pytest.MonkeyPatch()
from chisurf.plugins.core.setup.test import seeded
folder = seeded.prepare(tmp, mp)

import importlib.util
_spec = importlib.util.spec_from_file_location('emtk_port_parity', 'test/gui/emtk_port_parity.py')
_m = importlib.util.module_from_spec(_spec); sys.modules['emtk_port_parity'] = _m; _spec.loader.exec_module(_m)
emtk_screenshot = _m.emtk_screenshot
from chisurf.plugins.core.setup.gui.app import make_app

app = make_app(settings_dir=folder)
sizes = [tuple(int(v) for v in t.split('x')) for t in os.environ.get('CAP_SIZES', '1200x800,800x600').split(',')]
if os.environ.get('CAP_STATES_ONLY'):
    sizes = []
for size in sizes:
    for i, panel in enumerate(app.panels):
        if only and panel.key not in only:
            continue
        app.select(panel.key)
        name = "".join(c if c.isalnum() else "_" for c in panel.label).lower()
        emtk_screenshot(app, out / f"{prefix}_{i:02d}_{name}_{size[0]}x{size[1]}.png", size)
        print("wrote", panel.key, app.routes[panel.key], app.error)

if only or os.environ.get('CAP_NO_STATES'):
    raise SystemExit(0)
# hub states at 1200x800 (skipped when CAP_NO_STATES is set): search, help, guide, fast-forward finished
from chisurf.plugins.emtk_test_input import Driver
size = (1200, 800)
drv = Driver(app, size)
app.select("boarding"); drv.draw(3)
drv.click(app.item_rects["search"]); drv.type("plug"); drv.draw(2)
emtk_screenshot(app, out / f"{prefix}_state_search_plug_1200x800.png", size)
drv.app.filter = ""
drv.click(app.item_rects["help"]); emtk_screenshot(app, out / f"{prefix}_state_help_1200x800.png", size)
app.help.hide(); drv.draw(2)
drv.click(app.item_rects["guide"]); emtk_screenshot(app, out / f"{prefix}_state_guide_1200x800.png", size)
app.tour.stop(); drv.draw(2)
drv.click(app.item_rects["ff"])
for _ in range(40):
    drv.draw(1)
    if not app.fast_forward:
        break
emtk_screenshot(app, out / f"{prefix}_state_fastforward_done_1200x800.png", size)
print("status:", app.status)
