"""after.json for burst_h2mm covering every tab (the stock ``after`` draws only the first screen).

    python scripts/capture_after_inventory.py <out_dir>
Draws the app with each tab selected by a real click on its title, and merges the strings of all of them into the
inventory of ``emtk_port_parity after`` (which runs first, for the screenshots, the tooltip audit and the Qt-free check).
"""

import json
import sys
from pathlib import Path

from test.gui import emtk_port_parity as parity

from chisurf.plugins.burst.burst_h2mm.gui.native import create_app
from chisurf.plugins.emtk_test_input import Driver

out = Path(sys.argv[1])
parity.after("burst_h2mm", out)
data = json.loads((out / "after.json").read_text())
app = create_app()
drv = Driver(app)
controls = set(data["controls"])
for tab in ("Detector setup", "H2MM settings", "Dwell FRET", "Selection", "Decays", "LL scan", "TDP", "Dwell times", "State path"):
    drv.click_text(tab)
    painter = drv.draw(2)
    controls |= {parity.normalize(t[5]) for t in painter.texts}
controls.discard("")
data["controls"] = sorted(controls)
(out / "after.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
print(len(controls), "controls over all tabs")
